# Implementation Notes

- Skill ID: `skill-activation-and-workflow-trace`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P0`
- Capability: 记录 Skill 候选、选择理由、版本、节点、审批、失败和回滚。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
