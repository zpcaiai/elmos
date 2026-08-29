# Implementation Notes

- Skill ID: `audit-and-customer-evidence-export`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 导出脱敏 Trace、证据、SLO、数据血缘和认证报告。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
