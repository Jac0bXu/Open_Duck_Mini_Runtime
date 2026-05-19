import json
import struct

import eventlet


class DataReceiver:
    def __init__(self):
        self._greenthread = None
        self.is_running = False

    def start(self, hostname, port, socketio):
        self.stop()
        self.is_running = True
        self._greenthread = eventlet.spawn(
            self._run, hostname, port, socketio
        )

    def stop(self):
        self.is_running = False
        if self._greenthread:
            eventlet.kill(self._greenthread)
            self._greenthread = None

    def _run(self, hostname, port, socketio):
        # Retry -- robot takes ~10s to init before stream server is ready
        sock = None
        for attempt in range(30):
            if not self.is_running:
                return
            try:
                sock = eventlet.connect((hostname, port))
                socketio.emit("log_data", {"data": f"Connected to data stream on {hostname}:{port}"})
                break
            except Exception:
                if attempt == 0:
                    socketio.emit("log_data", {"data": f"Waiting for data stream on {hostname}:{port}..."})
                eventlet.sleep(1)
        else:
            socketio.emit("log_data", {"data": "Failed to connect to data stream after 30s"})
            self.is_running = False
            return

        recv_buffer = b""

        while self.is_running:
            try:
                while len(recv_buffer) < 4:
                    chunk = sock.recv(4 - len(recv_buffer))
                    if not chunk:
                        raise ConnectionError("Stream closed")
                    recv_buffer += chunk

                msg_len = struct.unpack("!I", recv_buffer[:4])[0]
                recv_buffer = recv_buffer[4:]

                while len(recv_buffer) < msg_len:
                    chunk = sock.recv(msg_len - len(recv_buffer))
                    if not chunk:
                        raise ConnectionError("Stream closed")
                    recv_buffer += chunk

                payload = recv_buffer[:msg_len]
                recv_buffer = recv_buffer[msg_len:]

                obs = json.loads(payload.decode("utf-8"))
                socketio.emit("obs_data", obs)

            except eventlet.Timeout:
                continue
            except (ConnectionError, OSError, json.JSONDecodeError) as e:
                if self.is_running:
                    socketio.emit("log_data", {"data": f"Data stream error: {e}"})
                break

        try:
            sock.close()
        except Exception:
            pass
        self.is_running = False
        socketio.emit("log_data", {"data": "Data stream disconnected"})
