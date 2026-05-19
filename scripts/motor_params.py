"""
    Using an open source lib: https://github.com/pollen-robotics/pypot@support-feetech-sts3215
    All register opereation are defined in class FeetechSTS3215IO, which is from: pypot\feetech\sts3215_io.py
"""
import argparse
from pypot.feetech import FeetechSTS3215IO
import time

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



parser = argparse.ArgumentParser(description="A dedicated program who works with important parameters of motors.")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--init', action="store_true", help='init with default parameters for all motors')
group.add_argument('--list', action="store_true", help='list parameters of all motors')
args = parser.parse_args()

io = FeetechSTS3215IO("/dev/ttyACM0")

if args.init:
    for motor_name, motor_id in ALL_MOTORS.items():
        print(f"Configuring motor: {motor_name} ({motor_id})...")

        io.set_lock({motor_id: 0}) # Addr (55)

        io.set_mode({motor_id: 0}) # Addr (33). Opened by Richard, original code commented out

        io.set_maximum_acceleration({motor_id: 0}) # Addr (85)
        io.set_acceleration({motor_id: 0}) # Addr (41)

        # io.set_maximum_velocity({current_id: 0}) # Addr (84)
        # io.set_goal_speed({current_id: 0}) # Addr (46)

        io.set_P_coefficient({motor_id: 32}) # Addr (21)
        io.set_I_coefficient({motor_id: 0}) # Addr (23)
        io.set_D_coefficient({motor_id: 0}) # Addr (22)

        io.set_max_voltage_limit({motor_id: 85}) # Addr (14), set max voltage to 8.5v, 飞特官方客服推荐值。

        io.set_lock({motor_id: 1}) # Addr (55)
        time.sleep(0.5)
        
        # input("Press ENTER to set this dof to 0 position ... Or press Ctrl+C to cancel")
        # io.set_goal_position({motor_id: 0})

        print('')

    print('All parameters are initialized!')
elif args.list:
    from rich.table import Table
    from rich.console import Console

    table = Table(title = 'Parameters of all motors', show_header=True, show_lines=True)

    table.add_column('Name', width = 15)
    table.add_column('ID', width = 3)
    table.add_column('Mode', width=4)
    table.add_column('Torque', width = 6)
    table.add_column('Accel', width = 5)
    table.add_column('MaxAccel', width = 8)
    table.add_column('MaxVel', width = 6)
    table.add_column('GoalSpd', width = 7)
    table.add_column('P', width = 3)
    table.add_column('I', width = 3)
    table.add_column('D', width = 3)
    table.add_column('MinVolt', width = 7)
    table.add_column('MaxVolt', width = 7)

    for motor_name, motor_id in ALL_MOTORS.items():
        print(f'Reading parameters of motor: {motor_name} ({motor_id})...')

        if motor_name.startswith('left_'):
            row_color = 'blue'
        elif motor_name.startswith('right_'):
            row_color = 'cyan'
        elif motor_name.startswith('neck_'):
            row_color = 'green'
        elif motor_name.startswith('head_'):
            row_color = 'yellow'
        else:
            row_color = 'white'

        table.add_row(
            motor_name,
            str(motor_id),
            str(io.get_mode({motor_id})[0]),
            str(io.is_torque_enabled({motor_id})[0]),
            str(io.get_acceleration({motor_id})[0]),
            str(io.get_maximum_acceleration({motor_id})[0]),
            str(io.get_maximum_velocity({motor_id})[0]),
            str(io.get_goal_speed({motor_id})[0]),
            str(io.get_P_coefficient({motor_id})[0]),
            str(io.get_I_coefficient({motor_id})[0]),
            str(io.get_D_coefficient({motor_id})[0]),
            str(io.get_min_voltage_limit({motor_id})[0]),
            str(io.get_max_voltage_limit({motor_id})[0]),
            style=row_color
        )
    print('\n')

    console = Console()
    console.print(table)    
