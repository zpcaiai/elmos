# Implementation Notes

- Skill ID: `security-incident-response-and-forensics`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 检测、隔离、回滚、保全证据、通知和复盘 AI/Agent 安全事件。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
