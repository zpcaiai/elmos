# Implementation Notes

- Skill ID: `cost-capacity-and-margin-forecast`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P1`
- Capability: 预测成本、容量、队列、收入、毛利和扩容需求。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
