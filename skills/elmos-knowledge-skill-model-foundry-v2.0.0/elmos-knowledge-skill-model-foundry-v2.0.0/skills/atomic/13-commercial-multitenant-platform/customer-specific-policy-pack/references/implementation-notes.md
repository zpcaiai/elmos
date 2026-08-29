# Implementation Notes

- Skill ID: `customer-specific-policy-pack`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P1`
- Capability: 把客户编码规范、安全、数据和上线要求封装为版本化策略包。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
