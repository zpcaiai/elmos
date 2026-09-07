# Implementation Notes

- Skill ID: `training-reproducibility-and-registry`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 记录代码、数据、容器、随机种子、依赖、硬件、指标与模型血缘。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
