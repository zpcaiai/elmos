# Implementation Notes

- Skill ID: `multi-objective-reward-contract`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 组合功能、等价、安全、证据、维护性、最小改动、时间和成本奖励。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
