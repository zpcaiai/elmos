# Implementation Notes

- Skill ID: `reviewer-calibration-and-gold-check`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 通过标准样本、盲测和一致性指标校准审阅质量。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
