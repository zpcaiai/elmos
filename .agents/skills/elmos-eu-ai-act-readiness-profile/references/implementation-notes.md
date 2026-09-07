# Implementation Notes

- Skill ID: `eu-ai-act-readiness-profile`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 按产品角色和风险场景维护透明度、文档、监控和事件响应准备度。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
