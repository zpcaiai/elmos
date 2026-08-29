# Implementation Notes

- Skill ID: `process-reward-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 对计划、工具选择、检查点、验证和恢复步骤进行过程级评分。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
