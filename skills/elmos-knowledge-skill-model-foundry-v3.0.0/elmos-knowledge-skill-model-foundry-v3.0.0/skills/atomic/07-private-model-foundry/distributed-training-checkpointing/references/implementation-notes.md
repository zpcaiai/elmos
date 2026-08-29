# Implementation Notes

- Skill ID: `distributed-training-checkpointing`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 支持 DDP/FSDP/ZeRO、并行保存、拓扑变化恢复和训练断点续跑。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
