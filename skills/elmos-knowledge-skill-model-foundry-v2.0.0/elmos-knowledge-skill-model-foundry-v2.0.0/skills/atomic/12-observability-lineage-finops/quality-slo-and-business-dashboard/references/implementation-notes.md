# Implementation Notes

- Skill ID: `quality-slo-and-business-dashboard`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 统一展示正确性、认证、延迟、可用性、成本、收入和毛利。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
