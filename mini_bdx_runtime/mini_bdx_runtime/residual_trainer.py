import glob
import numpy as np

from mini_bdx_runtime.residual_policy import ResidualMLP


class ResidualTrainer:
    def __init__(self, policy: ResidualMLP, lr=1e-4, gamma=0.99):
        self.policy = policy
        self.lr = lr
        self.gamma = gamma

    def compute_returns(self, rewards):
        returns = np.zeros_like(rewards)
        g = 0.0
        for t in reversed(range(len(rewards))):
            g = rewards[t] + self.gamma * g
            returns[t] = g
        return returns

    def train_on_episode(self, episode_data):
        obs = episode_data["obs"]
        noise = episode_data["noise"]
        rewards = episode_data["rewards"]

        returns = self.compute_returns(rewards)
        advantages = returns - np.mean(returns)
        std = np.std(returns) + 1e-8
        advantages = advantages / std

        T = len(rewards)
        accumulated_grads = None

        for t in range(T):
            self.policy.forward(obs[t])
            grad = advantages[t] * noise[t] / (self.policy.exploration_std ** 2)
            grads = self.policy.backward(grad)

            if accumulated_grads is None:
                accumulated_grads = {k: v.copy() for k, v in grads.items()}
            else:
                for k in accumulated_grads:
                    accumulated_grads[k] += grads[k]

        for k in accumulated_grads:
            accumulated_grads[k] /= T

        self.policy.apply_gradients(accumulated_grads, self.lr)

        return {
            "mean_reward": float(np.mean(rewards)),
            "mean_return": float(np.mean(returns)),
            "total_reward": float(np.sum(rewards)),
            "episode_length": T,
        }

    def train(self, data_dir, num_epochs=10):
        pattern = f"{data_dir}/episode_*.npz"
        files = sorted(glob.glob(pattern))
        if not files:
            print(f"No episode files found matching {pattern}")
            return []

        all_metrics = []
        for epoch in range(num_epochs):
            epoch_metrics = []
            for f in files:
                data = np.load(f, allow_pickle=True)
                episode_data = {
                    "obs": data["obs"],
                    "noise": data["noise"],
                    "rewards": data["rewards"],
                }
                metrics = self.train_on_episode(episode_data)
                epoch_metrics.append(metrics)

            avg_reward = np.mean([m["mean_reward"] for m in epoch_metrics])
            avg_length = np.mean([m["episode_length"] for m in epoch_metrics])
            print(
                f"Epoch {epoch + 1}/{num_epochs}: "
                f"avg_reward={avg_reward:.3f}, avg_length={avg_length:.0f}"
            )
            all_metrics.append(epoch_metrics)

        return all_metrics
