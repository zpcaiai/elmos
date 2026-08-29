# Implementation Notes

- Skill ID: `speculative-draft-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P2`
- Capability: 训练低成本草稿模型并验证其与目标模型的接受率和端到端收益。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
