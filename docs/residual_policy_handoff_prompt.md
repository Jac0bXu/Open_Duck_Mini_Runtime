# Copy-Paste Handoff Prompt

Paste the following into a new Claude Code session to continue the residual policy implementation:

---

```
You are continuing implementation of a residual policy system for the Open Duck Mini robot. Read the handoff document at `docs/residual_policy_handoff.md` for full context — it has the specs for all 3 remaining files.

Summary of what's done and what's left:
- DONE: `mini_bdx_runtime/mini_bdx_runtime/residual_policy.py` — ResidualMLP class (101→32→14, zero-init, tanh output, manual backprop)
- TODO 1: `mini_bdx_runtime/mini_bdx_runtime/residual_rewards.py` — IMU-based reward functions (upright, smooth, alive, velocity) + EpisodeMonitor class with fall detection
- TODO 2: `mini_bdx_runtime/mini_bdx_runtime/residual_trainer.py` — REINFORCE training loop (compute returns, advantages, update weights)
- TODO 3: `scripts/residual_walk.py` — Entry point subclassing RLWalk from `scripts/v2_rl_walk_mujoco.py` with collect/train/run CLI modes

Build in this order: rewards → trainer → entry point. No existing files should be modified. The approved plan is at `/Users/zhenghao/.claude/plans/serialized-wondering-storm.md`.

Key files to reference:
- `scripts/v2_rl_walk_mujoco.py` — the RLWalk class being subclassed (especially lines 199-342 for the run() method, line 282 is the integration point)
- `mini_bdx_runtime/mini_bdx_runtime/residual_policy.py` — the already-created MLP
- `mini_bdx_runtime/mini_bdx_runtime/raw_imu.py` — Imu.get_data() returns {"gyro": (3,), "accelero": (3,)}
```