# Implementation Notes

- Skill ID: `quality-cost-pareto-analysis`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P1`
- Capability: 比较模型、Skill、缓存和验证策略的质量—成本—时间前沿。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
