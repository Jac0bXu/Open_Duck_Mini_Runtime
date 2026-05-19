import json
import socket
import struct
import time
import threading

import numpy as np


class ObsStreamServer:
    def __init__(self, port=5678, max_rate_hz=20):
        self.host = "0.0.0.0"
        self.port = port
        self.max_rate_hz = max_rate_hz
        self.min_interval = 1.0 / max_rate_hz
        self.stop = False
        self.latest_obs = None
        self.obs_lock = threading.Lock()
        self.last_send_time = 0

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))

        threading.Thread(target=self._serve, daemon=True).start()
        print(f"ObsStreamServer listening on {self.host}:{self.port}")

    def push_obs(self, obs_dict: dict):
        with self.obs_lock:
            self.latest_obs = obs_dict

    def _serialize(self, data):
        def convert(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [convert(v) for v in obj]
            return obj

        return json.dumps(convert(data)).encode("utf-8")

    def _serve(self):
        while not self.stop:
            self.server_socket.listen(1)
            self.server_socket.settimeout(1.0)
            try:
                conn, address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            print(f"ObsStreamServer: client connected from {address}")
            try:
                while not self.stop:
                    now = time.time()
                    elapsed = now - self.last_send_time
                    if elapsed < self.min_interval:
                        time.sleep(self.min_interval - elapsed)

                    with self.obs_lock:
                        obs = self.latest_obs

                    if obs is None:
                        time.sleep(0.01)
                        continue

                    payload = self._serialize(obs)
                    header = struct.pack("!I", len(payload))
                    try:
                        conn.sendall(header + payload)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        break
                    self.last_send_time = time.time()
            except Exception as e:
                print(f"ObsStreamServer: client error: {e}")
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            print("ObsStreamServer: client disconnected, waiting for new connection")

        try:
            self.server_socket.close()
        except Exception:
            pass
        print("ObsStreamServer: stopped")
