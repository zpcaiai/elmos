# Implementation Notes

- Skill ID: `consent-purpose-and-secondary-use`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 验证收集目的、训练用途、跨租户聚合和二次使用是否获得授权。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
