# Implementation Notes

- Skill ID: `invoice-and-cost-evidence`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 生成可审计的账单明细、成本归因、税务字段和客户异议证据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
