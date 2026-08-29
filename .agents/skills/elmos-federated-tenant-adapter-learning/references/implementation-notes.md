# Implementation Notes

- Skill ID: `federated-tenant-adapter-learning`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P2`
- Capability: 在不集中原始数据的前提下聚合租户 Adapter 更新并防止反推。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
