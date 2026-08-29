# Implementation Notes

- Skill ID: `feature-entitlement-and-license`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 按套餐、合同、地区、私有部署和试用授予模型、Skill、并发和认证能力。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
