# Implementation Notes

- Skill ID: `environment-aware-action-masking`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 根据权限、状态、风险和依赖动态屏蔽非法或无效动作。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
