# Implementation Notes

- Skill ID: `rl-algorithm-abstraction`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P2`
- Capability: 支持 GRPO、RLOO、PPO、离线 RL 等算法并保持环境与奖励接口稳定。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
