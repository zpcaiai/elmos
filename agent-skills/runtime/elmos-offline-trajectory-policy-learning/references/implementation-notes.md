# Implementation Notes

- Skill ID: `offline-trajectory-policy-learning`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 从已验证历史轨迹学习，避免直接在生产环境探索。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
