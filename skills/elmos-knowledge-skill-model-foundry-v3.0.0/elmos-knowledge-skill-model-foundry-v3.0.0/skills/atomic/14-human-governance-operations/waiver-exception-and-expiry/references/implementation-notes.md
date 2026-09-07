# Implementation Notes

- Skill ID: `waiver-exception-and-expiry`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 允许受控例外，但必须包含理由、补偿控制、期限和复审。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
