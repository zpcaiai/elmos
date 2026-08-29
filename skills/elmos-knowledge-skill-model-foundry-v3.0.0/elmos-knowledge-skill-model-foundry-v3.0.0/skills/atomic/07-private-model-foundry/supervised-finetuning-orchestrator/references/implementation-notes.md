# Implementation Notes

- Skill ID: `supervised-finetuning-orchestrator`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 执行 SFT 数据验证、模板锁定、分布式训练、Checkpoint 与离线评测。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
