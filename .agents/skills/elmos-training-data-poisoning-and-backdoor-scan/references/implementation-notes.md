# Implementation Notes

- Skill ID: `training-data-poisoning-and-backdoor-scan`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 检测异常模式、触发器、标签投毒、来源集中和行为后门。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
