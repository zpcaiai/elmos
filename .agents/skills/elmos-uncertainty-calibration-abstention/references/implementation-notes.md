# Implementation Notes

- Skill ID: `uncertainty-calibration-abstention`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 校准置信度、风险阈值和拒答/升级机制，避免错误自动化。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
