# Implementation Notes

- Skill ID: `skill-pack-marketplace-governance`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P1`
- Capability: 管理内部、合作伙伴和客户 Skill 包的签名、定价、权限和责任。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
