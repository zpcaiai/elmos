# Implementation Notes

- Skill ID: `legal-hold-and-evidence-preservation`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 在争议或调查期间冻结相关版本、日志、数据和证据链。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
