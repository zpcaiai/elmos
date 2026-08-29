# Implementation Notes

- Skill ID: `wall-clock-eta-and-progress-model`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 基于仓库规模、历史节点、队列和失败概率预测机器执行 ETA 与进度。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
