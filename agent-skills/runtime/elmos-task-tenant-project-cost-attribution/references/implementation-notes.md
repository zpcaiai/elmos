# Implementation Notes

- Skill ID: `task-tenant-project-cost-attribution`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 把成本精确归属到任务、用户、项目、业务线、模型和 Skill。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
