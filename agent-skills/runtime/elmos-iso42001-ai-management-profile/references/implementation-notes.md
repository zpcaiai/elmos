# Implementation Notes

- Skill ID: `iso42001-ai-management-profile`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 建立 AI 管理体系所需的职责、风险、数据、监控和持续改进证据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
