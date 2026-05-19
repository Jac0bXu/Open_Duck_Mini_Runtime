import threading
import time

import paramiko

CONDA_INIT = (
    'source ~/miniconda3/etc/profile.d/conda.sh && conda activate base && '
)


class SSHManager:
    def __init__(self):
        self.client = None
        self.sftp = None
        self.hostname = None
        self._lock = threading.Lock()

    @property
    def is_connected(self):
        if self.client is None:
            return False
        transport = self.client.get_transport()
        return transport is not None and transport.is_active()

    def connect(self, hostname, username="pi", password=None, port=22):
        if self.is_connected:
            self.disconnect()

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.client.connect(
                hostname=hostname,
                username=username,
                password=password if password else None,
                port=port,
                timeout=10,
                allow_agent=True,
                look_for_keys=True,
            )
            self.sftp = self.client.open_sftp()
            self.hostname = hostname
            return True, ""
        except Exception as e:
            self.client = None
            self.sftp = None
            return False, str(e)

    def disconnect(self):
        with self._lock:
            if self.sftp:
                try:
                    self.sftp.close()
                except Exception:
                    pass
                self.sftp = None
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
            self.hostname = None

    def exec_command(self, cmd, timeout=30):
        if not self.is_connected:
            return -1, "", "Not connected"

        full_cmd = 'bash -lc "' + CONDA_INIT + cmd + '"'

        with self._lock:
            try:
                stdin, stdout, stderr = self.client.exec_command(full_cmd, timeout=timeout)
                exit_code = stdout.channel.recv_exit_status()
                out = stdout.read().decode("utf-8", errors="replace").strip()
                err = stderr.read().decode("utf-8", errors="replace").strip()
                return exit_code, out, err
            except Exception as e:
                return -1, "", str(e)

    def exec_command_async(self, cmd, on_stdout=None, on_stderr=None, on_done=None):
        full_cmd = 'bash -lc "' + CONDA_INIT + cmd + '"'

        def _run():
            if not self.is_connected:
                if on_done:
                    on_done(-1, "Not connected")
                return

            try:
                stdin, stdout, stderr = self.client.exec_command(full_cmd, timeout=None)
                stdout.channel.set_combine_stderr(True)

                while True:
                    line = stdout.readline()
                    if not line and stdout.channel.recv_exit_status() >= 0:
                        break
                    if line and on_stdout:
                        on_stdout(line.rstrip())

                exit_code = stdout.channel.recv_exit_status()
                if on_done:
                    on_done(exit_code, "")
            except Exception as e:
                if on_done:
                    on_done(-1, str(e))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def upload_file(self, local_path, remote_path):
        if not self.is_connected or self.sftp is None:
            return False, "Not connected"

        try:
            self.sftp.put(local_path, remote_path)
            return True, remote_path
        except Exception as e:
            return False, str(e)

    def check_bluetooth_controller(self):
        cmd = (
            'python3 -c "'
            "import pygame; pygame.init(); pygame.joystick.init(); "
            "print(pygame.joystick.get_count())"
            '"'
        )
        exit_code, out, err = self.exec_command(cmd, timeout=10)
        if exit_code == 0:
            try:
                lines = out.strip().split("\n")
                count = int(lines[-1])
                return count
            except (ValueError, IndexError):
                return -1
        return -1

    def is_walking(self):
        exit_code, out, err = self.exec_command(
            "pgrep -f v2_rl_walk_mujoco", timeout=5
        )
        return exit_code == 0 and len(out.strip()) > 0
