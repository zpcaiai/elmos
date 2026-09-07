# Implementation Notes

- Skill ID: `sla-slo-and-service-credit`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 把可用性、完成时间、恢复、数据丢失和质量承诺绑定补偿规则。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
