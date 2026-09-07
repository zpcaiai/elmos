# Implementation Notes

- Skill ID: `safety-constrained-agent-learning`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 把工具权限、审批、数据边界和禁止动作作为不可被奖励抵消的硬约束。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
