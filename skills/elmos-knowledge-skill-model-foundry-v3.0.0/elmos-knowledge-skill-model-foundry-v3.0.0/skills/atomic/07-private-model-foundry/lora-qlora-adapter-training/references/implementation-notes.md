# Implementation Notes

- Skill ID: `lora-qlora-adapter-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 以低秩 Adapter 训练业务线和租户能力，控制 Rank、目标层和量化误差。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
