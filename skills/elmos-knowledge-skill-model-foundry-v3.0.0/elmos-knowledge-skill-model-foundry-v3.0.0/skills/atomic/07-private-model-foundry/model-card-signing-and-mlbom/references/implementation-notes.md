# Implementation Notes

- Skill ID: `model-card-signing-and-mlbom`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 生成模型卡、限制、数据摘要、依赖 BOM、签名和供应链证明。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
