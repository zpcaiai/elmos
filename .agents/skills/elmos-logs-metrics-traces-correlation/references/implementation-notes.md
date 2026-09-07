# Implementation Notes

- Skill ID: `logs-metrics-traces-correlation`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 使用统一 ID 关联任务、模型、工具、仓库、部署和客户问题。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
