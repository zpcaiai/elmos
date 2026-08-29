# Implementation Notes

- Skill ID: `selective-model-unlearning`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 针对撤回数据、租户退出或风险样本执行选择性遗忘并验证残留。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
