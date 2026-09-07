# Implementation Notes

- Skill ID: `task-mutation-and-adversarial-env`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 变异需求、依赖、配置、数据和故障，训练鲁棒性和泛化。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
