import json
import os
import tempfile

from flask import Blueprint, request, jsonify, current_app

from gui.config import REMOTE_ONNX_DIR, REMOTE_SCRIPTS_DIR, REMOTE_REPO_DIR

api_bp = Blueprint("api", __name__)


def get_ssh():
    return current_app.config["ssh_manager"]


def get_socketio():
    return current_app.config["socketio"]


@api_bp.route("/api/connect", methods=["POST"])
def connect():
    data = request.json or {}
    hostname = data.get("hostname", "")
    username = data.get("username", "pi")
    password = data.get("password", "")
    port = int(data.get("port", 22))

    if not hostname:
        return jsonify({"connected": False, "error": "Hostname is required"}), 400

    ssh = get_ssh()
    success, error = ssh.connect(hostname, username, password, port)
    walking = False
    if success:
        walking = ssh.is_walking()
    return jsonify({"connected": success, "hostname": hostname, "error": error, "walking": walking})


@api_bp.route("/api/disconnect", methods=["POST"])
def disconnect():
    ssh = get_ssh()
    ssh.disconnect()
    return jsonify({"disconnected": True})


@api_bp.route("/api/upload-policy", methods=["POST"])
def upload_policy():
    if "policy_file" not in request.files:
        return jsonify({"uploaded": False, "error": "No file provided"}), 400

    f = request.files["policy_file"]
    if f.filename == "":
        return jsonify({"uploaded": False, "error": "No file selected"}), 400

    ssh = get_ssh()
    if not ssh.is_connected:
        return jsonify({"uploaded": False, "error": "Not connected to robot"}), 400

    remote_path = os.path.join(REMOTE_ONNX_DIR, os.path.basename(f.filename))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        success, result = ssh.upload_file(tmp_path, remote_path)
        os.unlink(tmp_path)
        if success:
            return jsonify({"uploaded": True, "remote_path": remote_path})
        else:
            return jsonify({"uploaded": False, "error": result}), 500
    except Exception as e:
        os.unlink(tmp_path)
        return jsonify({"uploaded": False, "error": str(e)}), 500


@api_bp.route("/api/list-onnx", methods=["GET"])
def list_onnx():
    ssh = get_ssh()
    if not ssh.is_connected:
        return jsonify({"files": []})

    exit_code, out, err = ssh.exec_command(
        "find ~ -maxdepth 3 -name '*.onnx' -type f 2>/dev/null | sort", timeout=10
    )
    if exit_code == 0 and out:
        files = [f for f in out.strip().split("\n") if f]
    else:
        files = []
    return jsonify({"files": files})


@api_bp.route("/api/bluetooth-status", methods=["GET"])
def bluetooth_status():
    ssh = get_ssh()
    if not ssh.is_connected:
        return jsonify({"controller_count": -1, "connected": False})

    count = ssh.check_bluetooth_controller()
    return jsonify({"controller_count": count, "connected": count > 0})


@api_bp.route("/api/turn-on", methods=["POST"])
def turn_on():
    ssh = get_ssh()
    if not ssh.is_connected:
        return jsonify({"success": False, "error": "Not connected to robot"}), 400

    socketio = get_socketio()
    socketio.emit("log_data", {"data": "Running turn_on.py on robot..."})

    exit_code, out, err = ssh.exec_command(
        f"cd {REMOTE_REPO_DIR} && python3 scripts/turn_on.py", timeout=15
    )

    if out:
        socketio.emit("log_data", {"data": out})
    if err:
        socketio.emit("log_data", {"data": f"stderr: {err}"})

    success = exit_code == 0
    return jsonify({"success": success, "output": out, "error": err})


@api_bp.route("/api/start-walk", methods=["POST"])
def start_walk():
    data = request.json or {}
    ssh = get_ssh()
    socketio = get_socketio()

    if not ssh.is_connected:
        return jsonify({"started": False, "error": "Not connected to robot"}), 400

    onnx_path = data.get("onnx_path", "")
    if not onnx_path:
        return jsonify({"started": False, "error": "ONNX path is required"}), 400

    parts = [
        f"cd {REMOTE_REPO_DIR}",
        "&&",
        "python3 scripts/v2_rl_walk_mujoco.py",
        f"--onnx_model_path {onnx_path}",
    ]

    duck_config_path = data.get("duck_config_path")
    if duck_config_path:
        parts.append(f"--duck_config_path {duck_config_path}")

    action_scale = data.get("action_scale")
    if action_scale is not None:
        parts.append(f"-a {action_scale}")

    p_val = data.get("p")
    if p_val is not None:
        parts.append(f"-p {p_val}")

    i_val = data.get("i")
    if i_val is not None:
        parts.append(f"-i {i_val}")

    d_val = data.get("d")
    if d_val is not None:
        parts.append(f"-d {d_val}")

    control_freq = data.get("control_freq")
    if control_freq is not None:
        parts.append(f"-c {control_freq}")

    pitch_bias = data.get("pitch_bias")
    if pitch_bias is not None:
        parts.append(f"--pitch_bias {pitch_bias}")

    stream_data = data.get("stream_data", False)
    if stream_data:
        parts.append("--stream_data")
        stream_port = data.get("stream_port", 5678)
        parts.append(f"--stream_port {stream_port}")

    cmd = " ".join(parts)

    # Read voltages before starting walk (serial port is still free)
    exit_code, out, err = ssh.exec_command(
        f"cd {REMOTE_REPO_DIR} && python3 scripts/check_voltage_json.py",
        timeout=10,
    )
    if exit_code == 0 and out:
        try:
            result = json.loads(out.strip().split("\n")[-1])
            if "voltages" in result:
                socketio.emit("voltage_data", {"voltages": result["voltages"]})
                socketio.emit("log_data", {"data": f"Pre-walk voltages: {result['voltages']}"})
        except (json.JSONDecodeError, IndexError):
            pass

    socketio.emit("log_data", {"data": f"Starting walk: {cmd}"})

    def on_stdout(line):
        socketio.emit("log_data", {"data": line})

    def on_done(exit_code, error):
        socketio.emit(
            "log_data", {"data": f"Walk process ended (exit code: {exit_code})"}
        )
        if error:
            socketio.emit("log_data", {"data": f"Error: {error}"})
        socketio.emit("walk_status", {"walking": False})

    ssh.exec_command_async(cmd, on_stdout=on_stdout, on_done=on_done)

    socketio.emit("walk_status", {"walking": True})

    if stream_data:
        stream_port_val = int(data.get("stream_port", 5678))
        current_app.config["data_receiver"].start(
            ssh.hostname, stream_port_val, socketio
        )

    return jsonify({"started": True, "command": cmd})


@api_bp.route("/api/stop-walk", methods=["POST"])
def stop_walk():
    ssh = get_ssh()
    socketio = get_socketio()

    if not ssh.is_connected:
        return jsonify({"stopped": False, "error": "Not connected to robot"}), 400

    ssh.exec_command("pkill -9 -f v2_rl_walk_mujoco", timeout=5)

    current_app.config["data_receiver"].stop()
    socketio.emit("walk_status", {"walking": False})
    socketio.emit("log_data", {"data": "Walk process stopped"})

    # Read voltages after walk stops (serial port is free again)
    import time; time.sleep(1)
    exit_code, out, err = ssh.exec_command(
        f"cd {REMOTE_REPO_DIR} && python3 scripts/check_voltage_json.py",
        timeout=10,
    )
    if exit_code == 0 and out:
        try:
            result = json.loads(out.strip().split("\n")[-1])
            if "voltages" in result:
                socketio.emit("voltage_data", {"voltages": result["voltages"]})
                socketio.emit("log_data", {"data": f"Post-walk voltages: {result['voltages']}"})
        except (json.JSONDecodeError, IndexError):
            pass

    return jsonify({"stopped": True})


@api_bp.route("/api/check-voltage", methods=["POST"])
def check_voltage():
    ssh = get_ssh()
    socketio = get_socketio()

    if not ssh.is_connected:
        return jsonify({"error": "Not connected to robot"}), 400

    socketio.emit("log_data", {"data": "Reading motor voltages..."})

    exit_code, out, err = ssh.exec_command(
        f"cd {REMOTE_REPO_DIR} && python3 scripts/check_voltage_json.py",
        timeout=10,
    )

    if exit_code != 0 or not out:
        msg = err or "Failed to read voltages"
        socketio.emit("log_data", {"data": f"Voltage check failed: {msg}"})
        return jsonify({"error": msg}), 500

    try:
        result = json.loads(out.strip().split("\n")[-1])
    except (json.JSONDecodeError, IndexError):
        socketio.emit("log_data", {"data": f"Voltage parse error: {out}"})
        return jsonify({"error": "Failed to parse voltage output"}), 500

    if "error" in result:
        socketio.emit("log_data", {"data": f"Voltage check error: {result['error']}"})
        return jsonify({"error": result["error"]}), 500

    socketio.emit("log_data", {"data": f"Voltages: {result['voltages']}"})
    socketio.emit("voltage_data", {"voltages": result["voltages"]})
    return jsonify({"voltages": result["voltages"]})


@api_bp.route("/api/status", methods=["GET"])
def status():
    ssh = get_ssh()
    connected = ssh.is_connected
    walking = False
    if connected:
        walking = ssh.is_walking()

    streaming = current_app.config["data_receiver"].is_running

    return jsonify(
        {
            "connected": connected,
            "hostname": ssh.hostname,
            "walking": walking,
            "streaming": streaming,
        }
    )
