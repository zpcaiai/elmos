# Implementation Notes

- Skill ID: `code-reranker-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 训练针对仓库检索、版本约束和证据相关性的重排器。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
