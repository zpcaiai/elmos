# Implementation Notes

- Skill ID: `model-data-knowledge-drift`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 监控输入、输出、失败、知识时效、数据分布和能力指标漂移。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
