# Implementation Notes

- Skill ID: `model-extraction-membership-audit`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 评估模型抽取、成员推断和训练数据记忆风险。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
