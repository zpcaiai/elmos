# Implementation Notes

- Skill ID: `router-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 训练任务、Skill、模型、风险、成本和人工审批路由模型。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
