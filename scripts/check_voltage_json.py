"""Read motor voltages via pypot and output JSON. Intended to be called via SSH."""
import json
import sys

from pypot.feetech import FeetechSTS3215IO

joints = {
    "left_hip_yaw": 20,
    "left_hip_roll": 21,
    "left_hip_pitch": 22,
    "left_knee": 23,
    "left_ankle": 24,
    "neck_pitch": 30,
    "head_pitch": 31,
    "head_yaw": 32,
    "head_roll": 33,
    "right_hip_yaw": 10,
    "right_hip_roll": 11,
    "right_hip_pitch": 12,
    "right_knee": 13,
    "right_ankle": 14,
}

try:
    io = FeetechSTS3215IO("/dev/ttyACM0", baudrate=1000000, use_sync_read=True)
    raw = io.get_present_voltage(list(joints.values()))
    voltages = [round(v * 0.1, 2) for v in raw]
    print(json.dumps({"voltages": voltages}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)
