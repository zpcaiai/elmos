# Implementation Notes

- Skill ID: `adapter-reward-evaluator-drift`
- Pack: `12-observability-lineage-finops`
- Kernel: `Cross-Cutting Observability and Economics Plane`
- Priority: `P1`
- Capability: 监控租户 Adapter、奖励函数和模型裁判随时间的偏移。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
