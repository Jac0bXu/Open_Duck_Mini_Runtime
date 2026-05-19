# Residual Policy Implementation — Handoff Document

**Date:** 2026-05-18
**Branch:** `train`
**Status:** 1 of 4 files complete, 3 remaining

## Project Goal

The trained walking policy from MuJoCo simulation doesn't transfer perfectly to the real robot (tends to fall forward). We're building a small numpy-only residual MLP that runs on the Raspberry Pi alongside the frozen ONNX policy. It outputs tiny corrections (±0.05 rad) to adapt the gait from real IMU feedback, trained on-robot via REINFORCE.

## Approved Plan

Full plan at: `/Users/zhenghao/.claude/plans/serialized-wondering-storm.md`

## File Status

| # | File | Status | Notes |
|---|------|--------|-------|
| 1 | `mini_bdx_runtime/mini_bdx_runtime/residual_policy.py` | **DONE** | ResidualMLP class, 108 lines |
| 2 | `mini_bdx_runtime/mini_bdx_runtime/residual_rewards.py` | **TODO** | Reward functions from IMU data |
| 3 | `mini_bdx_runtime/mini_bdx_runtime/residual_trainer.py` | **TODO** | REINFORCE training loop |
| 4 | `scripts/residual_walk.py` | **TODO** | Entry point with collect/train/run modes |

**No existing files are modified.** The entry point subclasses `RLWalk` from `scripts/v2_rl_walk_mujoco.py`.

---

## File 1: `residual_policy.py` (DONE)

Already created and complete at `mini_bdx_runtime/mini_bdx_runtime/residual_policy.py`. Contains:
- `ResidualMLP` class: 2-layer MLP (101→32→14), zero-initialized weights
- `forward(obs)` → correction vector (14,), clipped to ±0.05 via tanh
- `forward_with_exploration(obs, rng)` → noisy correction + noise tuple
- `backward(grad_output)` → manual backprop returning dict of gradients
- `apply_gradients(grads, lr)` → SGD update
- `get_params()`, `save(path)`, `load(path)` → npz format

---

## File 2: `residual_rewards.py` (TODO)

**Purpose:** Compute step rewards from real IMU data. No position sensor needed.

### Required Components

| Function | Weight | Formula | Purpose |
|----------|--------|---------|---------|
| `compute_upright_reward(accelero)` | 2.0 | `cos(angle between accel vector and [0,0,-1])` | Penalize falling |
| `compute_smooth_reward(gyro)` | 0.5 | `exp(-||gyro|| / 2.0)` | Penalize shaking |
| `compute_alive_reward()` | 0.1 | `+1` constant | Survive longer |
| `compute_velocity_reward(accelero, command_x)` | 1.0 | `sign match between forward accel and command` | Follow commands |

### `compute_step_reward(gyro, accelero, commands) -> (float, dict)`
Combines all components with their weights, returns total reward and component dict.

### `EpisodeMonitor` class
Tracks episode state across steps:
- `step(gyro, accelero, commands)` → (reward, done)
- Fall detection: `upright < 0.3` for 5 consecutive steps → `done=True`
- `reset()` → clear counters
- Stores `total_reward`, `step_count`

### Input Sources
- `gyro`: from `Imu.get_data()["gyro"]` — shape (3,)
- `accelero`: from `Imu.get_data()["accelero"]` — shape (3,)
- `commands`: shape (7,) — [vel_x, vel_y, vel_theta, neck_pitch, head_pitch, head_yaw, head_roll]

---

## File 3: `residual_trainer.py` (TODO)

**Purpose:** REINFORCE training loop that runs on the Pi using collected episode data.

### Required Components

```python
class ResidualTrainer:
    def __init__(self, policy: ResidualMLP, lr=1e-4, gamma=0.99):
        ...
    
    def compute_returns(self, rewards: np.ndarray) -> np.ndarray:
        """Discounted returns: R_t = r_t + gamma * R_{t+1}"""
        ...
    
    def train_on_episode(self, episode_data: dict) -> dict:
        """
        episode_data keys: 'obs' [T,101], 'noise' [T,14], 'rewards' [T]
        
        For each timestep:
          1. Forward pass: policy.forward(obs[t])
          2. Compute advantage: return[t] - baseline (mean return)
          3. Gradient: advantage[t] * noise[t] / exploration_std^2
          4. Backprop through MLP: policy.backward(grad)
          5. Accumulate gradients
        
        Apply averaged gradients at end of episode.
        Returns metrics dict (mean_reward, mean_return, etc.)
        """
        ...
    
    def train(self, data_dir: str, num_epochs: int = 10) -> list:
        """Load all episode_*.npz from data_dir, train for num_epochs."""
        ...
```

### Key Implementation Detail

The REINFORCE gradient for each step is:
```
grad = advantage[t] * noise[t] / exploration_std^2
```
This is passed through `policy.backward(grad)` which returns gradients for W1, b1, W2, b2. Gradients are averaged over the episode length before applying.

---

## File 4: `scripts/residual_walk.py` (TODO)

**Purpose:** Entry point that subclasses `RLWalk` and adds residual policy integration.

### Architecture

```python
class ResidualRLWalk(RLWalk):
    """Adds residual policy to the base RLWalk."""
    
    def __init__(self, ..., residual_weights=None, collect=False, 
                 data_dir=None, max_episodes=10, exploration_std=0.02):
        super().__init__(...)
        from mini_bdx_runtime.residual_policy import ResidualMLP
        from mini_bdx_runtime.residual_rewards import EpisodeMonitor
        
        self.residual = ResidualMLP(exploration_std=exploration_std)
        if residual_weights:
            self.residual.load(residual_weights)
        
        self.collect_mode = collect
        self.episode_monitor = EpisodeMonitor()
        self.data_dir = data_dir
        self.max_episodes = max_episodes
        self.episode_data = []  # list of dicts
        self.episode_count = 0
    
    def run(self):
        """Override parent run() to insert residual."""
        # Copy the parent's run() method structure (lines 199-342 of v2_rl_walk_mujoco.py)
        # but modify the action computation:
        #
        # At the point where parent does:
        #   action = self.policy.infer(obs)          # line 282
        # Insert:
        #   base_action = action.copy()
        #   if self.collect_mode:
        #       correction, noise = self.residual.forward_with_exploration(obs)
        #       # store obs, base_action, correction, noise for episode
        #   else:
        #       correction = self.residual.forward(obs)
        #       noise = None
        #   action = base_action + correction
        #   # then continue with action history, motor_targets, etc.
        #
        # After motor targets are set, compute reward:
        #   imu_data = self.imu.get_data()  # already available
        #   reward, done = self.episode_monitor.step(
        #       imu_data["gyro"], imu_data["accelero"], self.last_commands
        #   )
        #   if self.collect_mode:
        #       store step data
        #   if done:
        #       save episode, reset
        ...
```

### Three CLI Modes

**Run mode (default):**
```bash
python scripts/residual_walk.py --onnx_model_path ~/model.onnx --residual_weights residual_weights.npz
```

**Collect mode:**
```bash
python scripts/residual_walk.py --onnx_model_path ~/model.onnx --collect --max_episodes 5 --data_dir residual_data/run1
```

**Train mode:**
```bash
python scripts/residual_walk.py --train --data_dir residual_data/run1 --residual_weights residual_weights.npz --num_epochs 10
```

### Integration Point (Critical)

The residual must be inserted at line 282 of `v2_rl_walk_mujoco.py`, between ONNX inference and action history update:

```python
# Line 282 original:
action = self.policy.infer(obs)

# Becomes:
base_action = self.policy.infer(obs)
correction = self.residual.forward(obs)  # or forward_with_exploration in collect mode
action = base_action + correction

# Lines 284-290 unchanged:
self.last_last_last_action = self.last_last_action.copy()
self.last_last_action = self.last_action.copy()
self.last_action = action.copy()
self.motor_targets = self.init_pos + action * self.action_scale
```

`last_action` tracks the combined action (base + residual), so the observation correctly reflects the residual's effect.

### Head Overlay

Head commands happen AFTER the residual (lines 310-311 unchanged):
```python
head_motor_targets = self.last_commands[3:] + self.motor_targets[5:9]
self.motor_targets[5:9] = head_motor_targets
```
The residual's corrections to head joints (indices 5-8) get overridden by head commands, which is fine — the residual should focus on leg adjustments.

### Safety
- Correction always clipped to ±0.05 rad (2.9°) via tanh * max_correction in ResidualMLP
- Zero-initialized weights mean no correction without training
- Xbox pause/resume works as before

---

## Key Reference Files

| File | What to know |
|------|-------------|
| `scripts/v2_rl_walk_mujoco.py` | `RLWalk` class to subclass (lines 25-342). `get_obs()` at line 123, `run()` at line 199, action computation at lines 282-290, head overlay at 310-311 |
| `mini_bdx_runtime/mini_bdx_runtime/onnx_infer.py` | `OnnxInfer` interface — `infer(obs)` returns action (14,) |
| `mini_bdx_runtime/mini_bdx_runtime/rl_utils.py` | `make_action_dict()`, `LowPassActionFilter` |
| `mini_bdx_runtime/mini_bdx_runtime/raw_imu.py` | `Imu.get_data()` returns dict with `"gyro"` (3,) and `"accelero"` (3,) |
| `mini_bdx_runtime/mini_bdx_runtime/residual_policy.py` | Already created — the MLP to use |
| `mini_bdx_runtime/mini_bdx_runtime/feet_contacts.py` | `FeetContacts.get()` returns contact array (2,) |
| `mini_bdx_runtime/mini_bdx_runtime/poly_reference_motion.py` | `PolyReferenceMotion` for phase calculation |

## Observation Space (101 dims)

```
[0:3]   gyro (3)
[3:6]   accelero (3)
[6:13]  commands (7) — [vel_x, vel_y, vel_theta, neck_pitch, head_pitch, head_yaw, head_roll]
[13:27] dof_pos - init_pos (14)
[27:41] dof_vel * 0.05 (14)
[41:55] last_action (14)
[55:69] last_last_action (14)
[69:83] last_last_last_action (14)
[83:97] motor_targets (14)
[97:99] feet_contacts (2)
[99:101] imitation_phase (2) — [cos, sin]
```

## Workflow After Implementation

1. **Verify no regression:** Run without weights file → motor targets identical to original
2. **Collect:** Place robot on floor, run collect mode, let it walk (and fall), repeat for N episodes
3. **Train:** Run train mode on collected data
4. **Deploy:** Run with trained weights, observe improved stability
5. **Iterate:** Collect more data with improved policy, retrain

## Implementation Order

Recommended order to build the remaining 3 files:
1. `residual_rewards.py` — standalone, no dependencies on other TODO files
2. `residual_trainer.py` — depends on residual_policy.py (done) and residual_rewards.py
3. `scripts/residual_walk.py` — depends on all three above; the main integration point
