# Implementation Notes

- Skill ID: `cost-aware-agent-policy`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 把 Token、工具、GPU 和 Wall-clock 预算纳入动作价值与终止决策。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
