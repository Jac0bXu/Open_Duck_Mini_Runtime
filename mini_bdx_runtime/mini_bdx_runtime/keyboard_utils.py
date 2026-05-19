"""
Usage: 
    Step 1. from keyboard_utils import is_esc_pressed
    Step 2. if is_esc_pressed(): ...
"""

import sys
import os
import termios
import fcntl
import time

def is_key_pressed(keycode):
    return is_any_key_pressed([keycode])

def is_any_key_pressed(keycode_list):
    # 保存当前终端设置
    old_attr = termios.tcgetattr(sys.stdin)
    old_flags = fcntl.fcntl(sys.stdin, fcntl.F_GETFL)

    try:
        # 设置非阻塞和原始模式
        new_attr = old_attr[:]
        new_attr[3] = new_attr[3] & ~termios.ICANON & ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_attr)

        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)
        
        # 尝试读取一个字符
        try:
            ch = sys.stdin.read(1)
            if ch in keycode_list:
                # clear buffer
                while sys.stdin.read(1024):
                    pass

                return ch
        except IOError:
            return None
        # 恢复终端设置
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_attr)
        fcntl.fcntl(sys.stdin, fcntl.F_SETFL, old_flags)

    return None

# 主循环示例
if __name__ == "__main__":
    try:
        print("Working... Press ESC to exit...")
        while True:
            """ Single key capture """
            if is_key_pressed('\x1b') is not None:
                print("ESC key was pressed!")
                break

            time.sleep(0.1)  # 模拟工作

        print("Working... Press any number to exit...")
        while True:
            """ Multiple keys capture """
            number_keycodes = [chr(i) for i in range(48, 58)]
            ret = is_any_key_pressed(number_keycodes)
            if ret is not None:
                print(f"{ret} was pressed!")
                break

            time.sleep(0.1)  # 模拟工作
    except KeyboardInterrupt:
        print("\nProgram terminated by user")