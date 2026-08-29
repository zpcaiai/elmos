# Implementation Notes

- Skill ID: `nist-ai-rmf-control-profile`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 将 Govern、Map、Measure、Manage 映射到 Elmos 控制与证据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
