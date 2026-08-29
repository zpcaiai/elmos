# Implementation Notes

- Skill ID: `sensitive-content-capture-policy`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 默认不采集 Prompt、代码和工具内容，按明确授权进行过滤、截断或加密采集。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
