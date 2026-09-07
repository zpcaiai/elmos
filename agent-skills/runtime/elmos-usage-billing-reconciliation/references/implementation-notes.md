# Implementation Notes

- Skill ID: `usage-billing-reconciliation`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 对模型、GPU、工具和退款事件去重、汇总并与供应商账单对账。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
