# Implementation Notes

- Skill ID: `soc2-iso27001-evidence-profile`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 复用身份、变更、访问、备份、监控和事件证据支持企业审计。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
