# Implementation Notes

- Skill ID: `training-run-and-checkpoint-trace`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 记录数据版本、代码、镜像、硬件、超参、Checkpoint、失败和恢复。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
