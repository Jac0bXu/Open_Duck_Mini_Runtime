"""UDP walk: off-board inference client for Open Duck Mini V2.

Sends observations to a remote inference server (Mac) over UDP, receives
action chunks, and consumes them one-per-tick at the control frequency.

The background prefetch thread fetches the next chunk while the main control
loop keeps consuming, so the main loop never blocks on UDP.

Usage:
  python scripts/udp_walk.py --server_host 192.168.1.100

The server side runs:
  python -m diffusion.udp_inference_server --onnx path/to/policy.onnx
"""

import argparse
import os
import socket
import struct
import threading
import time
from collections import deque

import numpy as np

from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.raw_imu import Imu
from mini_bdx_runtime.poly_reference_motion import PolyReferenceMotion
from mini_bdx_runtime.xbox_controller import XBoxController
from mini_bdx_runtime.feet_contacts import FeetContacts
from mini_bdx_runtime.rl_utils import make_action_dict
from mini_bdx_runtime.duck_config import DuckConfig

HOME_DIR = os.path.expanduser("~")

# ── protocol constants (must match udp_inference_server.py) ───────────────────
MAGIC_REQ = b"DUCK"
MAGIC_RES = b"QUAK"
OBS_DIM = 101
ACTION_DIM = 14
CHUNK_SIZE = 16
DEFAULT_SERVER_PORT = 7777

# Trigger a background fetch when this many actions remain in the buffer.
# Must satisfy: REFILL_THRESHOLD * (1/control_freq) > expected UDP RTT
# e.g. 4 actions × 50ms = 200ms headroom > typical 40ms RTT → never blocks.
DEFAULT_REFILL_THRESHOLD = 4


# ── UDP client ────────────────────────────────────────────────────────────────

class UDPActionClient:
    """Sends obs to the Mac inference server; returns action chunks."""

    def __init__(self, host: str, port: int = DEFAULT_SERVER_PORT, timeout: float = 0.5):
        self.addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(timeout)
        self._seq = 0

    def request_chunk(self, obs: np.ndarray, max_retries: int = 3) -> np.ndarray | None:
        """Send obs, block until action chunk received. Returns (CHUNK_SIZE, ACTION_DIM) or None."""
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        header = struct.pack("!4sIH", MAGIC_REQ, self._seq, len(obs))
        packet = header + obs.astype(np.float32).tobytes()

        for attempt in range(max_retries):
            self._sock.sendto(packet, self.addr)
            try:
                data, _ = self._sock.recvfrom(65535)
            except socket.timeout:
                print(f"[udp] timeout (attempt {attempt + 1}/{max_retries})")
                continue
            if len(data) < 12 or data[:4] != MAGIC_RES:
                continue
            if struct.unpack_from("!I", data, 4)[0] != self._seq:
                continue  # stale
            chunk_size = struct.unpack_from("!H", data, 8)[0]
            action_dim = struct.unpack_from("!H", data, 10)[0]
            n = chunk_size * action_dim
            if len(data) < 12 + n * 4:
                continue
            return np.frombuffer(data[12:12 + n * 4], dtype=np.float32).reshape(chunk_size, action_dim).copy()

        return None


# ── async prefetcher ──────────────────────────────────────────────────────────

class _AsyncPrefetcher:
    """Background thread that keeps the action buffer topped up.

    The main loop calls update_obs() every tick (non-blocking).  When the
    buffer falls to refill_threshold the worker wakes up, sends the latest obs
    to the server, and appends the returned chunk to the buffer.  The main loop
    calls pop_action() to consume one action per tick — it never waits on UDP.
    """

    def __init__(self, client: UDPActionClient, refill_threshold: int = DEFAULT_REFILL_THRESHOLD):
        self._client = client
        self._refill_threshold = refill_threshold
        self._buffer: deque[np.ndarray] = deque()
        self._lock = threading.Lock()
        self._latest_obs: np.ndarray | None = None
        self._fetch_needed = threading.Event()
        self._running = False
        self._thread = threading.Thread(target=self._worker, daemon=True, name="udp-prefetch")

    def start(self) -> None:
        self._running = True
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._fetch_needed.set()

    def update_obs(self, obs: np.ndarray) -> None:
        """Called every control tick. Stores latest obs and wakes worker if buffer is low."""
        self._latest_obs = obs.copy()
        with self._lock:
            if len(self._buffer) <= self._refill_threshold:
                self._fetch_needed.set()

    def pop_action(self) -> np.ndarray | None:
        with self._lock:
            return self._buffer.popleft() if self._buffer else None

    def buffer_len(self) -> int:
        with self._lock:
            return len(self._buffer)

    def _worker(self) -> None:
        while self._running:
            self._fetch_needed.wait(timeout=0.1)
            self._fetch_needed.clear()

            obs = self._latest_obs
            if obs is None or not self._running:
                continue

            chunk = self._client.request_chunk(obs)
            if chunk is None:
                # Retry immediately on failure so we don't starve the buffer
                self._fetch_needed.set()
                continue

            with self._lock:
                for action in chunk:
                    self._buffer.append(action)


# ── walk controller ───────────────────────────────────────────────────────────

class UDPWalk:
    def __init__(
        self,
        server_host: str,
        server_port: int = DEFAULT_SERVER_PORT,
        duck_config_path: str = f"{HOME_DIR}/duck_config.json",
        serial_port: str = "/dev/ttyACM0",
        control_freq: float = 50.0,
        pid: list[int] = None,
        action_scale: float = 0.25,
        commands: bool = True,
        pitch_bias: float = 0.0,
        refill_threshold: int = DEFAULT_REFILL_THRESHOLD,
    ):
        if pid is None:
            pid = [30, 0, 0]

        self.duck_config = DuckConfig(config_json_path=duck_config_path)
        self.commands = commands
        self.pitch_bias = pitch_bias
        self.action_scale = action_scale
        self.control_freq = control_freq

        self.num_dofs = 14
        self.max_motor_velocity = 5.24  # rad/s
        self.dof_vel_scale = 0.05

        udp_client = UDPActionClient(server_host, server_port)
        self._prefetcher = _AsyncPrefetcher(udp_client, refill_threshold=refill_threshold)

        self.hwi = HWI(self.duck_config, serial_port)
        self._start_motors(pid)

        self.imu = Imu(
            sampling_freq=int(self.control_freq),
            user_pitch_bias=self.pitch_bias,
            upside_down=self.duck_config.imu_upside_down,
        )
        self.feet_contacts = FeetContacts()

        self.init_pos = list(self.hwi.init_pos.values())
        self.motor_targets = np.array(self.init_pos, dtype=np.float64)
        self.prev_motor_targets = self.motor_targets.copy()
        self.last_action = np.zeros(self.num_dofs)
        self.last_last_action = np.zeros(self.num_dofs)
        self.last_last_last_action = np.zeros(self.num_dofs)

        self.last_commands = [0.0] * 7
        self.paused = self.duck_config.start_paused

        self.command_freq = 20
        if self.commands:
            self.xbox_controller = XBoxController(self.command_freq)

        self.PRM = PolyReferenceMotion(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "polynomial_coefficients.pkl")
        )
        self.imitation_i = 0.0
        self.imitation_phase = np.array([1.0, 0.0])

    def _start_motors(self, pid: list[int]) -> None:
        kps = [pid[0]] * self.num_dofs
        kds = [pid[2]] * self.num_dofs
        kps[5:9] = [8, 8, 8, 8]
        self.hwi.set_kps(kps)
        self.hwi.set_kds(kds)
        self.hwi.turn_on()
        time.sleep(2)

    def get_obs(self) -> np.ndarray | None:
        imu_data = self.imu.get_data()

        dof_pos = self.hwi.get_present_positions(ignore=["left_antenna", "right_antenna"])
        dof_vel = self.hwi.get_present_velocities(ignore=["left_antenna", "right_antenna"])

        if dof_pos is None or dof_vel is None:
            return None
        if len(dof_pos) != self.num_dofs or len(dof_vel) != self.num_dofs:
            return None

        gyro = np.array(imu_data["gyro"], dtype=np.float32)
        accelero = np.array(imu_data["accelero"], dtype=np.float32)
        if np.any(np.isnan(gyro)) or np.any(np.isnan(accelero)):
            return None

        feet_contacts = self.feet_contacts.get()

        return np.concatenate([
            gyro,                                   # 3
            accelero,                               # 3
            self.last_commands,                     # 7
            dof_pos - self.init_pos,                # 14
            dof_vel * self.dof_vel_scale,           # 14
            self.last_action,                       # 14
            self.last_last_action,                  # 14
            self.last_last_last_action,             # 14
            self.motor_targets,                     # 14
            feet_contacts,                          # 2
            self.imitation_phase,                   # 2
        ]).astype(np.float32)                       # total = 101

    def run(self) -> None:
        print("Waiting for first action chunk...")
        self._prefetcher.start()

        # Warm up: collect real obs and feed to prefetcher until buffer is ready.
        # (prefetcher needs at least one obs to trigger the first fetch)
        while self._prefetcher.buffer_len() == 0:
            obs = self.get_obs()
            if obs is not None:
                self._prefetcher.update_obs(obs)
            time.sleep(0.01)
        print(f"Buffer ready ({self._prefetcher.buffer_len()} actions). Starting walk loop.")

        _empty_count = 0
        try:
            while True:
                t = time.time()

                if self.commands:
                    self.last_commands, buttons, _, _ = self.xbox_controller.get_last_command()
                    if buttons.A.triggered:
                        self.paused = not self.paused
                        print("PAUSED" if self.paused else "RUNNING")

                if self.paused:
                    time.sleep(0.1)
                    continue

                obs = self.get_obs()
                if obs is None:
                    time.sleep(1 / self.control_freq)
                    continue

                # Non-blocking: give latest obs to prefetcher, get next action
                self._prefetcher.update_obs(obs)
                action = self._prefetcher.pop_action()

                if action is None:
                    _empty_count += 1
                    if _empty_count % 10 == 1:
                        print(f"[udp_walk] buffer empty #{_empty_count}, holding last action")
                    action = self.last_action.copy()
                else:
                    _empty_count = 0

                self.last_last_last_action = self.last_last_action.copy()
                self.last_last_action = self.last_action.copy()
                self.last_action = action.copy()

                self.imitation_i = (self.imitation_i + 1.0) % self.PRM.nb_steps_in_period
                self.imitation_phase = np.array([
                    np.cos(self.imitation_i / self.PRM.nb_steps_in_period * 2 * np.pi),
                    np.sin(self.imitation_i / self.PRM.nb_steps_in_period * 2 * np.pi),
                ])

                self.motor_targets = np.array(self.init_pos) + action * self.action_scale
                self.motor_targets = np.clip(
                    self.motor_targets,
                    self.prev_motor_targets - self.max_motor_velocity / self.control_freq,
                    self.prev_motor_targets + self.max_motor_velocity / self.control_freq,
                )
                self.prev_motor_targets = self.motor_targets.copy()

                self.motor_targets[5:9] += np.array(self.last_commands[3:7])

                self.hwi.set_position_all(make_action_dict(self.motor_targets, list(self.hwi.joints.keys())))

                elapsed = time.time() - t
                budget = 1.0 / self.control_freq
                time.sleep(max(0.0, budget - elapsed))

        except KeyboardInterrupt:
            pass
        finally:
            self._prefetcher.stop()
            self.feet_contacts.stop()
            print("TURNING OFF")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="UDP walk: off-board inference client")
    parser.add_argument("--server_host", type=str, required=True, help="Mac IP address")
    parser.add_argument("--server_port", type=int, default=DEFAULT_SERVER_PORT)
    parser.add_argument("--duck_config_path", type=str, default=f"{HOME_DIR}/duck_config.json")
    parser.add_argument("--serial_port", type=str, default="/dev/ttyACM0")
    parser.add_argument("--control_freq", type=float, default=50.0)
    parser.add_argument("-p", type=int, default=30, dest="kp")
    parser.add_argument("-d", type=int, default=0, dest="kd")
    parser.add_argument("-a", "--action_scale", type=float, default=0.25)
    parser.add_argument("--pitch_bias", type=float, default=0.0)
    parser.add_argument("--no_commands", action="store_true", help="Disable Xbox controller")
    parser.add_argument(
        "--refill_threshold", type=int, default=DEFAULT_REFILL_THRESHOLD,
        help="Prefetch when this many actions remain (default 4 → ~80ms headroom at 50Hz)",
    )
    args = parser.parse_args()

    walker = UDPWalk(
        server_host=args.server_host,
        server_port=args.server_port,
        duck_config_path=args.duck_config_path,
        serial_port=args.serial_port,
        control_freq=args.control_freq,
        pid=[args.kp, 0, args.kd],
        action_scale=args.action_scale,
        commands=not args.no_commands,
        pitch_bias=args.pitch_bias,
        refill_threshold=args.refill_threshold,
    )
    walker.run()


if __name__ == "__main__":
    main()
