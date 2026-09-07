# Implementation Notes

- Skill ID: `differential-private-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P2`
- Capability: 对确有必要的敏感训练应用差分隐私并量化效用损失。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
