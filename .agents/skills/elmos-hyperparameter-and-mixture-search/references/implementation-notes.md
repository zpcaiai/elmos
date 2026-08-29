# Implementation Notes

- Skill ID: `hyperparameter-and-mixture-search`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 在预算约束下优化学习率、Rank、数据混合、长度和训练策略。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
