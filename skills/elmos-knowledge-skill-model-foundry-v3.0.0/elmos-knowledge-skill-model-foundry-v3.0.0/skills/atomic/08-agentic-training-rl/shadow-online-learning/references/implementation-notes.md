# Implementation Notes

- Skill ID: `shadow-online-learning`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P2`
- Capability: 在影子环境收集新分布经验，完成离线认证后再更新生产策略。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
