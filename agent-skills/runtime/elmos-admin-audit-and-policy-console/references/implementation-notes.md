# Implementation Notes

- Skill ID: `admin-audit-and-policy-console`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 提供租户、权限、用量、模型、Skill、知识、风险和审计统一控制台。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
