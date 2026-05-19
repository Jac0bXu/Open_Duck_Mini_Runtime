import numpy as np


def compute_upright_reward(accelero):
    up = np.array([0, 0, -1])
    a = accelero / (np.linalg.norm(accelero) + 1e-8)
    return float(np.dot(a, up))


def compute_smooth_reward(gyro):
    return float(np.exp(-np.linalg.norm(gyro) / 2.0))


def compute_alive_reward():
    return 1.0


def compute_velocity_reward(accelero, command_x):
    forward_accel = accelero[0]
    if abs(command_x) < 0.01:
        return 0.0
    return float(np.sign(forward_accel) == np.sign(command_x))


REWARD_WEIGHTS = {
    "upright": 2.0,
    "smooth": 0.5,
    "alive": 0.1,
    "velocity": 1.0,
}


def compute_step_reward(gyro, accelero, commands):
    components = {
        "upright": compute_upright_reward(accelero),
        "smooth": compute_smooth_reward(gyro),
        "alive": compute_alive_reward(),
        "velocity": compute_velocity_reward(accelero, commands[0]),
    }
    total = sum(REWARD_WEIGHTS[k] * v for k, v in components.items())
    return total, components


class EpisodeMonitor:
    FALL_THRESHOLD = 0.3
    FALL_PATIENCE = 5

    def __init__(self, max_steps=5000):
        self.max_steps = max_steps
        self.reset()

    def reset(self):
        self.total_reward = 0.0
        self.step_count = 0
        self._fall_count = 0
        self._last_components = {}

    def step(self, gyro, accelero, commands):
        reward, components = compute_step_reward(gyro, accelero, commands)
        self._last_components = components
        self.total_reward += reward
        self.step_count += 1

        if components["upright"] < self.FALL_THRESHOLD:
            self._fall_count += 1
        else:
            self._fall_count = 0

        done = self._fall_count >= self.FALL_PATIENCE or self.step_count >= self.max_steps
        return reward, done
