# Implementation Notes

- Skill ID: `policy-simulation-and-impact`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 在发布策略前模拟允许/拒绝变化、误伤率和权限爆炸半径。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
