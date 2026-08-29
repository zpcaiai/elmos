# Implementation Notes

- Skill ID: `semantic-transformer-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 训练基于 Semantic IR 的代码生成、迁移、重构和跨语言变换能力。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
