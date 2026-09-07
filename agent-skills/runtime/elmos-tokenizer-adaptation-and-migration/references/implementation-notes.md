# Implementation Notes

- Skill ID: `tokenizer-adaptation-and-migration`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P2`
- Capability: 受控扩展词表并处理 Embedding 初始化、兼容、Checkpoint 迁移和回归。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
