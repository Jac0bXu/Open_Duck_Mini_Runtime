import os
import time
import argparse
import numpy as np

HOME_DIR = os.path.expanduser("~")

from v2_rl_walk_mujoco import RLWalk
from mini_bdx_runtime.residual_policy import ResidualMLP
from mini_bdx_runtime.residual_rewards import EpisodeMonitor
from mini_bdx_runtime.residual_trainer import ResidualTrainer


class ResidualRLWalk(RLWalk):
    def __init__(
        self,
        residual_weights=None,
        collect=False,
        data_dir=None,
        max_episodes=10,
        exploration_std=0.02,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.residual = ResidualMLP(exploration_std=exploration_std)
        if residual_weights:
            self.residual.load(residual_weights)

        self.collect_mode = collect
        self.episode_monitor = EpisodeMonitor()
        self.data_dir = data_dir
        self.max_episodes = max_episodes

        self._episode_obs = []
        self._episode_noise = []
        self._episode_rewards = []
        self.episode_count = 0

        if self.data_dir:
            os.makedirs(self.data_dir, exist_ok=True)

    def _save_episode(self):
        if not self._episode_obs:
            return
        path = os.path.join(
            self.data_dir, f"episode_{self.episode_count:04d}.npz"
        )
        np.savez(
            path,
            obs=np.array(self._episode_obs),
            noise=np.array(self._episode_noise),
            rewards=np.array(self._episode_rewards),
        )
        print(
            f"Episode {self.episode_count} saved: "
            f"{len(self._episode_rewards)} steps, "
            f"reward={self.episode_monitor.total_reward:.2f} -> {path}"
        )
        self.episode_count += 1

    def _reset_episode(self):
        self._episode_obs = []
        self._episode_noise = []
        self._episode_rewards = []
        self.episode_monitor.reset()

    def run(self):
        i = 0
        try:
            print("Starting residual walk")
            start_t = time.time()
            while True:
                left_trigger = 0
                right_trigger = 0
                t = time.time()

                if self.commands:
                    (
                        self.last_commands,
                        self.buttons,
                        left_trigger,
                        right_trigger,
                    ) = self.xbox_controller.get_last_command()
                    if self.buttons.dpad_up.triggered:
                        self.phase_frequency_factor_offset += 0.05
                        print(
                            f"Phase frequency factor offset {round(self.phase_frequency_factor_offset, 3)}"
                        )

                    if self.buttons.dpad_down.triggered:
                        self.phase_frequency_factor_offset -= 0.05
                        print(
                            f"Phase frequency factor offset {round(self.phase_frequency_factor_offset, 3)}"
                        )

                    if self.buttons.LB.is_pressed:
                        self.phase_frequency_factor = 1.3
                    else:
                        self.phase_frequency_factor = 1.0

                    if self.buttons.X.triggered:
                        if self.duck_config.projector:
                            self.projector.switch()

                    if self.buttons.B.triggered:
                        if self.duck_config.speaker:
                            self.sounds.play_random_sound()

                    if self.duck_config.antennas:
                        self.antennas.set_position_left(right_trigger)
                        self.antennas.set_position_right(left_trigger)

                    if self.buttons.A.triggered:
                        self.paused = not self.paused
                        if self.paused:
                            print("PAUSE")
                        else:
                            print("UNPAUSE")

                if self.paused:
                    time.sleep(0.1)
                    continue

                obs = self.get_obs()
                if obs is None:
                    continue

                self.imitation_i += 1 * (
                    self.phase_frequency_factor + self.phase_frequency_factor_offset
                )
                self.imitation_i = self.imitation_i % self.PRM.nb_steps_in_period
                self.imitation_phase = np.array(
                    [
                        np.cos(
                            self.imitation_i
                            / self.PRM.nb_steps_in_period
                            * 2
                            * np.pi
                        ),
                        np.sin(
                            self.imitation_i
                            / self.PRM.nb_steps_in_period
                            * 2
                            * np.pi
                        ),
                    ]
                )

                if self.save_obs:
                    self.saved_obs.append(obs)

                if self.replay_obs is not None:
                    if i < len(self.replay_obs):
                        obs = self.replay_obs[i]
                    else:
                        print("BREAKING ")
                        break

                # --- Residual integration ---
                base_action = self.policy.infer(obs)

                if self.collect_mode:
                    correction, noise = self.residual.forward_with_exploration(obs)
                else:
                    correction = self.residual.forward(obs)
                    noise = None

                action = base_action + correction

                self.last_last_last_action = self.last_last_action.copy()
                self.last_last_action = self.last_action.copy()
                self.last_action = action.copy()

                self.motor_targets = self.init_pos + action * self.action_scale

                if self.action_filter is not None:
                    self.action_filter.push(self.motor_targets)
                    filtered_motor_targets = self.action_filter.get_filtered_action()
                    if time.time() - start_t > 1:
                        self.motor_targets = filtered_motor_targets

                self.prev_motor_targets = self.motor_targets.copy()

                head_motor_targets = self.last_commands[3:] + self.motor_targets[5:9]
                self.motor_targets[5:9] = head_motor_targets

                action_dict = make_action_dict(
                    self.motor_targets, list(self.hwi.joints.keys())
                )

                self.hwi.set_position_all(action_dict)

                # --- Episode monitoring ---
                imu_data = self.imu.get_data()
                reward, done = self.episode_monitor.step(
                    imu_data["gyro"],
                    imu_data["accelero"],
                    self.last_commands,
                )

                if self.collect_mode:
                    self._episode_obs.append(obs.copy())
                    self._episode_noise.append(noise)
                    self._episode_rewards.append(reward)

                if done and self.collect_mode:
                    self._save_episode()
                    self._reset_episode()
                    if self.episode_count >= self.max_episodes:
                        print(f"Collected {self.max_episodes} episodes, stopping.")
                        break

                i += 1

                took = time.time() - t
                if (1 / self.control_freq - took) < 0:
                    print(
                        "Policy control budget exceeded by",
                        np.around(took - 1 / self.control_freq, 3),
                    )
                time.sleep(max(0, 1 / self.control_freq - took))

        except KeyboardInterrupt:
            if self.collect_mode and self._episode_obs:
                self._save_episode()
            if self.duck_config.antennas:
                self.antennas.stop()
            if self.duck_config.eyes:
                self.eyes.stop()
            if self.duck_config.projector:
                self.projector.stop()
            self.feet_contacts.stop()

        if self.save_obs:
            import pickle

            pickle.dump(self.saved_obs, open("robot_saved_obs.pkl", "wb"))
        print("TURNING OFF")


def train_mode(args):
    policy = ResidualMLP()
    if args.residual_weights:
        policy.load(args.residual_weights)
    trainer = ResidualTrainer(policy, lr=1e-4, gamma=0.99)
    trainer.train(args.data_dir, num_epochs=args.num_epochs)
    output = args.output or "residual_weights.npz"
    policy.save(output)
    print(f"Weights saved to {output}")


def main():
    parser = argparse.ArgumentParser(description="Residual policy walk")
    sub = parser.add_subparsers(dest="mode")

    # Run / collect args
    run_parser = argparse.ArgumentParser(add_help=False)
    run_parser.add_argument("--onnx_model_path", type=str, required=True)
    run_parser.add_argument("--duck_config_path", type=str, default=f"{HOME_DIR}/duck_config.json")
    run_parser.add_argument("-a", "--action_scale", type=float, default=0.25)
    run_parser.add_argument("-p", type=int, default=30)
    run_parser.add_argument("-i", type=int, default=0)
    run_parser.add_argument("-d", type=int, default=0)
    run_parser.add_argument("-c", "--control_freq", type=int, default=50)
    run_parser.add_argument("--pitch_bias", type=float, default=0)
    run_parser.add_argument("--commands", action="store_true", default=True)
    run_parser.add_argument("--cutoff_frequency", type=float, default=None)
    run_parser.add_argument("--residual_weights", type=str, default=None)
    run_parser.add_argument("--exploration_std", type=float, default=0.02)

    # Collect mode
    collect_parser = sub.add_parser("collect", parents=[run_parser])
    collect_parser.add_argument("--max_episodes", type=int, default=10)
    collect_parser.add_argument("--data_dir", type=str, default="residual_data/run1")

    # Run mode (default)
    run_sub = sub.add_parser("run", parents=[run_parser])

    # Train mode
    train_parser = sub.add_parser("train")
    train_parser.add_argument("--data_dir", type=str, required=True)
    train_parser.add_argument("--residual_weights", type=str, default=None)
    train_parser.add_argument("--num_epochs", type=int, default=10)
    train_parser.add_argument("--output", type=str, default=None)

    args = parser.parse_args()

    if args.mode == "train":
        train_mode(args)
        return

    pid = [args.p, args.i, args.d]

    collect_mode = args.mode == "collect"
    data_dir = args.data_dir if collect_mode else None
    max_episodes = args.max_episodes if collect_mode else 10

    walker = ResidualRLWalk(
        residual_weights=args.residual_weights,
        collect=collect_mode,
        data_dir=data_dir,
        max_episodes=max_episodes,
        exploration_std=args.exploration_std,
        onnx_model_path=args.onnx_model_path,
        duck_config_path=args.duck_config_path,
        action_scale=args.action_scale,
        pid=pid,
        control_freq=args.control_freq,
        commands=args.commands,
        pitch_bias=args.pitch_bias,
        cutoff_frequency=args.cutoff_frequency,
    )
    walker.run()


if __name__ == "__main__":
    main()
