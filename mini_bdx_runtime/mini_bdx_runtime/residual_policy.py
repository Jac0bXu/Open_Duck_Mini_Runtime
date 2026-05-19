import numpy as np


class ResidualMLP:
    """Small 2-layer MLP that outputs residual corrections to a base policy.

    Zero-initialized so it starts as identity (no correction). Output is
    clipped to +/- max_correction via tanh scaling.
    """

    def __init__(
        self,
        obs_dim=101,
        hidden_dim=32,
        action_dim=14,
        max_correction=0.05,
        exploration_std=0.02,
    ):
        self.obs_dim = obs_dim
        self.hidden_dim = hidden_dim
        self.action_dim = action_dim
        self.max_correction = max_correction
        self.exploration_std = exploration_std
        self._init_weights()

    def _init_weights(self):
        self.W1 = np.zeros((self.obs_dim, self.hidden_dim))
        self.b1 = np.zeros(self.hidden_dim)
        self.W2 = np.zeros((self.hidden_dim, self.action_dim))
        self.b2 = np.zeros(self.action_dim)

    def forward(self, obs):
        self._last_obs = obs.copy()
        self._h_pre = obs @ self.W1 + self.b1
        self._h = np.maximum(self._h_pre, 0)  # ReLU
        self._out_raw = np.tanh(self._h @ self.W2 + self.b2)
        return self._out_raw * self.max_correction

    def forward_with_exploration(self, obs, rng=None):
        deterministic = self.forward(obs)
        if rng is not None:
            noise = rng.normal(0, self.exploration_std, self.action_dim)
        else:
            noise = np.random.normal(0, self.exploration_std, self.action_dim)
        correction = np.clip(
            deterministic + noise * self.max_correction,
            -self.max_correction,
            self.max_correction,
        )
        return correction, noise

    def backward(self, grad_output):
        d_out_raw = grad_output * self.max_correction
        d_tanh = (1 - self._out_raw**2) * d_out_raw

        dW2 = np.outer(self._h, d_tanh)
        db2 = d_tanh

        d_h = d_tanh @ self.W2.T
        d_h = d_h * (self._h_pre > 0).astype(float)

        dW1 = np.outer(self._last_obs, d_h)
        db1 = d_h

        return {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2}

    def apply_gradients(self, grads, lr=1e-4):
        self.W1 -= lr * grads["W1"]
        self.b1 -= lr * grads["b1"]
        self.W2 -= lr * grads["W2"]
        self.b2 -= lr * grads["b2"]

    def get_params(self):
        return {
            "W1": self.W1.copy(),
            "b1": self.b1.copy(),
            "W2": self.W2.copy(),
            "b2": self.b2.copy(),
        }

    def save(self, path):
        if not path.endswith(".npz"):
            path += ".npz"
        np.savez(
            path,
            W1=self.W1,
            b1=self.b1,
            W2=self.W2,
            b2=self.b2,
            obs_dim=self.obs_dim,
            hidden_dim=self.hidden_dim,
            action_dim=self.action_dim,
            max_correction=self.max_correction,
        )

    def load(self, path):
        if not path.endswith(".npz"):
            path += ".npz"
        data = np.load(path)
        self.W1 = data["W1"]
        self.b1 = data["b1"]
        self.W2 = data["W2"]
        self.b2 = data["b2"]
        self.obs_dim = int(data["obs_dim"])
        self.hidden_dim = int(data["hidden_dim"])
        self.action_dim = int(data["action_dim"])
        self.max_correction = float(data["max_correction"])
