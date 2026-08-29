# Implementation Notes

- Skill ID: `rlvr-code-agent-training`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 使用可执行测试、差分和证明信号进行可验证奖励强化学习。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
