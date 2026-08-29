# Implementation Notes

- Skill ID: `repository-planner-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 训练仓库理解、任务拆解、影响范围、检查点和执行 DAG 能力。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
