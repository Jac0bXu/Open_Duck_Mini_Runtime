# Open Duck Mini Runtime

## Raspberry Pi zero 2W setup

### Install Raspberry Pi OS

Download Raspberry Pi OS Lite (64-bit) from here : https://www.raspberrypi.com/software/operating-systems/

Follow the instructions here to install the OS on the SD card : https://www.raspberrypi.com/documentation/computers/getting-started.html

With the Raspberry Pi Imager, you can pre-configure session, wifi and ssh. Do it like below :

![imager_setup](https://github.com/user-attachments/assets/7a4987b2-de83-41dd-ab7f-585259685f16)

> Tip: I configure the rasp to connect to my phone's hotspot, this way I can connect to it from anywhere.

### Setup SSH (If not setup during the installation)

When first booting on the rasp, you will need to connect a screen and a keyboard. The first thing you should do is connect to a wifi network and enable SSH.

To do so, you can follow this guide : https://www.raspberrypi.com/documentation/computers/configuration.html#setting-up-wifi

Then, you can connect to your rasp using SSH without having to plug a screen and a keyboard.

### Update the system and install necessary stuff

```bash
sudo apt update
sudo apt upgrade
sudo apt install git
sudo apt install python3-pip
sudo apt install python3-virtualenvwrapper
(optional) sudo apt install python3-picamzero

```

Add this to the end of the `.bashrc`:

```bash
export WORKON_HOME=$HOME/.virtualenvs
export PROJECT_HOME=$HOME/Devel
source /usr/share/virtualenvwrapper/virtualenvwrapper.sh
```

### Enable I2C

`sudo raspi-config` -> `Interface Options` -> `I2C`

TODO set 400KHz ?

### Set the usbserial latency timer

```bash
cd  /etc/udev/rules.d/
sudo touch 99-usb-serial.rules
sudo nano 99-usb-serial.rules
# copy the following line in the file
SUBSYSTEM=="usb-serial", DRIVER=="ftdi_sio", ATTR{latency_timer}="1"
```

### Set the udev rules for the motor control board

TODO


### Setup xbox one controller over bluetooth

Turn your xbox one controller on and set it in pairing mode by long pressing the sync button on the top of the controller.

Run the following commands on the rasp :

```bash
bluetoothctl
scan on
```

Wait for the controller to appear in the list, then run :

```bash
pair <controller_mac_address>
trust <controller_mac_address>
connect <controller_mac_address>
```

The led on the controller should stop blinking and stay on.

You can test that it's working by running

```bash
python3 mini_bdx_runtime/mini_bdx_runtime/xbox_controller.py
```

## Speaker wiring and configuration
Follow this tutorial

> For now, don't activate `/dev/zero` when they ask

https://learn.adafruit.com/adafruit-max98357-i2s-class-d-mono-amp?view=all


## Install the runtime

### Make a virtual environment and activate it

```bash
mkvirtualenv -p python3 open-duck-mini-runtime
workon open-duck-mini-runtime
```

Clone this repository on your rasp, cd into the repo, then :

```bash
git clone https://github.com/apirrone/Open_Duck_Mini_Runtime
cd Open_Duck_Mini_Runtime
git checkout v2
pip install -e .
```

In Raspberry Pi 5, you need to perform the following operations

```bash
pip uninstall -y RPi.GPIO
pip install lgpio
```


## Test the IMU

```bash
python3 mini_bdx_runtime/mini_bdx_runtime/raw_imu.py
```

You can also run `python3 scripts/imu_server.py` on the robot and `python3 scripts/imu_client.py --ip <robot_ip>` on your computer to check that the frame is oriented correctly.

> To find the ip address of the robot, run `ifconfig` on the robot

### Calibrate the IMU

If the IMU is installed upside down:

```bash
python3 scripts/calibrate_imu.py
```

## Test motors

This will allow you to verify all your motors are connected and configured.

```bash
python3 scripts/check_motors.py
```

### Check motor voltages

```bash
python3 scripts/check_voltage.py
```

### Motor configuration and calibration

```bash
# View or set motor parameters (PID, voltage limits, acceleration, etc.)
python3 scripts/motor_params.py

# Set all motors to their initial standing position
python3 scripts/motor_init_pos.py

# Set motors to their logical zero position
python3 scripts/motor_logical_zero.py

# Configure a single motor
python3 scripts/configure_motor.py

# Configure all motors with default settings
python3 scripts/configure_all_motors.py
```

## Make your duck_config.json

Copy `example_config.json` in the home directory of your duck and rename it `duck_config.json`.

`cp example_config.json ~/duck_config.json`

In this file, you can configure some stuff, like registering if you installed the expression features, installed the imu upside down or and other stuff. You also write the joints offsets of your duck here

## Find the joints offsets

This script will guide you through finding the joints offsets of your robot that you can then write in your `duck_config.json`

> This procedure won't be necessary in the future as we will be flashing the offsets directly in each motor's eeprom.

```bash
cd scripts/
python find_soft_offsets.py
```

## Run the walk !

Download the [latest policy checkpoint ](https://github.com/apirrone/Open_Duck_Mini/blob/v2/BEST_WALK_ONNX_2.onnx) and copy it to your duck.

`cd scripts/`

`python v2_rl_walk_mujoco.py --onnx_model_path <path_to>/BEST_WALK_ONNX_2.onnx`

With real-time data streaming to the GUI dashboard:

`python v2_rl_walk_mujoco.py --onnx_model_path <path_to>/BEST_WALK_ONNX_2.onnx --stream_data --stream_port 5678`

```
- The commands are : 
- A to pause/unpause
- X to turn on/off the projector
- B to play a random sound
- Y to turn on/off head control (very experimental, I don't recommend trying that, it can break your duck's head)
- left and right triggers to control the left and right antennas
- LB (new!) press and hold to increase the walking frequency, kind of a sprint mode 🙂
```

### Auto-start walking on controller connection

The robot can automatically start walking when a Bluetooth controller connects:

```bash
python3 scripts/start_walk_after_controller.py --onnx_model_path <path_to>/BEST_WALK_ONNX_2.onnx
```

Or as a startup service using the shell script:

```bash
bash scripts/start_walk_after_controller.sh
```

### Turn on/off the robot

```bash
python3 scripts/turn_on.py
python3 scripts/turn_off.py
```

### Record and plot data

```bash
# Record motor/sensor data
python3 scripts/record_data.py

# Plot recorded data
python3 scripts/plot_recorded_data.py
```

## GUI Dashboard

A web-based dashboard for remote control, monitoring, and policy deployment. Runs on your laptop and connects to the robot via SSH.

### Start the dashboard

```bash
pip install -r gui/requirements.txt
python3 -c "import sys, os; sys.path.insert(0, '.'); from gui.app import create_app; app, socketio = create_app(); socketio.run(app, host='0.0.0.0', port=5001, debug=False)"
```

Open http://localhost:5001 in your browser.

### Features

- **SSH Connection** — Connect to the robot by IP, manage multiple saved connections
- **Policy Upload** — Upload ONNX policy files directly to the robot
- **Robot Controls** — Turn on, start/stop walking, configure action scale, PID, and control frequency
- **Real-time Charts** — Joint positions, motor targets, IMU gyroscope/accelerometer, feet contacts, and command inputs streamed at 20Hz over TCP
- **Motor Voltages** — Read all 14 servo voltages via the "Check Voltage" button (uses pypot, works when the robot is idle). Voltages are also automatically checked before and after each walk session
- **Bluetooth Status** — Monitor connected controller count
- **Console Log** — Real-time output from the robot's walking process

## Other scripts

| Script | Description |
|--------|-------------|
| `scripts/head_puppet.py` | Control the robot's head using an Xbox controller |
| `scripts/antennas_controller_test.py` | Test antenna control via Xbox controller |
| `scripts/cam_test.py` | Test Raspberry Pi camera capture |
| `scripts/fc_test.py` | Test Feetech motor connectivity and parameters |
| `scripts/obs_stream_server.py` | TCP server that streams observation data (used by the GUI dashboard) |
| `scripts/check_voltage_json.py` | Read motor voltages as JSON (used by the GUI dashboard) |