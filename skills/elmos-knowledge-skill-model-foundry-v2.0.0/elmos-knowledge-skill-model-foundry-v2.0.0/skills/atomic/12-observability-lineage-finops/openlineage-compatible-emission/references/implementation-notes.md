# Implementation Notes

- Skill ID: `openlineage-compatible-emission`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 以 Dataset、Job、Run 和 Facet 表达数据与模型流水线血缘。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
