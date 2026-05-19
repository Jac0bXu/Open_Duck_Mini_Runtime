import json
import os
import time
from pypot.feetech import FeetechSTS3215IO
import argparse
from mini_bdx_runtime.keyboard_utils import is_any_key_pressed

ALL_MOTORS = {
    "left_hip_yaw": 20,
    "left_hip_roll": 21,
    "left_hip_pitch": 22,
    "left_knee": 23,
    "left_ankle": 24,

    "right_hip_yaw": 10,
    "right_hip_roll": 11,
    "right_hip_pitch": 12,
    "right_knee": 13,
    "right_ankle": 14,

    "neck_pitch": 30,
    "head_pitch": 31,
    "head_yaw": 32,
    "head_roll": 33,
}

def go_logical_zero_pos(io):
    P = 4
    print(f'Set kp to {P} first for safety...')
    io.set_P_coefficient({motor_id: P for motor_id in ALL_MOTORS.values()})

    print('Moving all motors to their logical zero pos...')
    io.set_goal_position({motor_id: 0 for motor_id in ALL_MOTORS.values()})

    time.sleep(1)

    P = 32
    print(f'Set kp to {P} then...')
    io.set_P_coefficient({motor_id: P for motor_id in ALL_MOTORS.values()})

    print('')

    print('Now all motors are in logical zero pos! Press ESC or q to disable torque and quit...', end='', flush=True)
    while is_any_key_pressed(['\x1b', 'q']) == None:
        time.sleep(0.1)
    print('')

    print('Disable torque and quit!')
    io._set_torque_enable({motor_id: 0 for motor_id in ALL_MOTORS.values()})

def apply_single_motor(io, motor_id):
    print(f'\tScanning motor ({motor_id})...')

    try:
        old_offset = io.get_offset([motor_id])[0]
    except Exception as e:
        print(f"\tCould not find motor. Exception: {e}")
        return

    io.set_lock({motor_id: 0})
    io._set_torque_enable({motor_id: 128})
    time.sleep(0.1) # must sleep due to experience, otherwise timeout.
    io.set_lock({motor_id: 1})

    updated_offset = io.get_offset([motor_id])[0]
    print(f'\tMid pos offset updated: {old_offset} -> {updated_offset}')

def export_to_file(io, filename):
    if os.path.exists(filename) == True:
        print(f"File {filename} already exists.")
        return

    offsets = io.get_offset(ALL_MOTORS.values())
    data = {joint_name: offset for joint_name, offset in zip(ALL_MOTORS.keys(), offsets)}    

    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
        f.write('\n')

    print(f'Export to {filename} ok!')

def import_from_file(io, filename):
    if os.path.exists(filename) == False:
        print(f"File {filename} not found.")
        return

    print(f'Loading offsets from {filename}...')
    with open(filename, 'r') as f:
        data = json.load(f)
    print("{")
    for key, value in data.items():
        print(f"    {key}: {value},")
    print("}")
    print('')

    print('Unlocking EEPROM...')
    motor_locks = {motor_id: 0 for motor_id in ALL_MOTORS.values()}
    io.set_lock(motor_locks)
    print('')

    print('Writing offsets...')
    motor_offsets = {motor_id: data[joint_name] for joint_name, motor_id in ALL_MOTORS.items()}
    io.set_offset(motor_offsets)
    print('')

    print('Locking EEPROM...')
    motor_locks = {motor_id: 1 for motor_id in ALL_MOTORS.values()}
    io.set_lock(motor_locks)
    print('')

    go_logical_zero_pos(io)



parser = argparse.ArgumentParser(description="A dedicated program who works with motors' logical zero pos (AKA: mid pos).")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--go_zero', action="store_true", help='move all motors to their logical zero pos')
group.add_argument('--apply_current', action="store_true", help='apply the current motors\' positions as motors\' new logical zero pos')
group.add_argument('--export', metavar='filename', help='export current motors\' logical zero pos to a file for backup')
group.add_argument('--import', metavar='filename', dest='import_', help='import from a file and apply the data as the motors\' new logical zero pos')
args = parser.parse_args()

io = FeetechSTS3215IO('/dev/ttyACM0')

if args.go_zero:
    go_logical_zero_pos(io)
elif args.apply_current:
    for joint_name, motor_id in ALL_MOTORS.items():
        print(f'Applying motor ({joint_name}: {motor_id})...')
        apply_single_motor(io, motor_id)
        print('')

    print('All motors\' logical zero pos were reset to their current positions!')
elif args.export is not None:
    export_to_file(io, args.export)
elif args.import_ is not None:
    import_from_file(io, args.import_)
