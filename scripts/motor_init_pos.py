from mini_bdx_runtime.rustypot_position_hwi import HWI
from mini_bdx_runtime.duck_config import DuckConfig
import time
from datetime import datetime
from mini_bdx_runtime.keyboard_utils import is_any_key_pressed

duck_config = DuckConfig()

hwi = HWI(duck_config)
hwi.turn_on()

print('Press ESC or q to quit, torque will still be enabled...')
try:
    while(1):
        wait_seconds = 0
        while True:
            if is_any_key_pressed(['\x1b', 'q']):
                exit(0)

            PER_WAIT = 0.1
            time.sleep(PER_WAIT)
            wait_seconds += PER_WAIT
            if wait_seconds > 0.5:
                break

        while True:
            try:
                duck_config = DuckConfig()
                break
            except KeyboardInterrupt:
                print('Quit')
                exit(0)
            except BaseException as e:
                print(f'Read config failed, {e}')
                time.sleep(0.1)
                continue

        hwi.joints_offsets = duck_config.joints_offset # apply new joints offsets
        hwi.set_position_all(hwi.init_pos)

        current_time = datetime.now()
        formatted_time = current_time.strftime("%H:%M:%S.%f")[:-3]
        print(f'\rNew joint offset applied at {formatted_time}', end='')
except KeyboardInterrupt:
    print('Quit')
    exit(0)
