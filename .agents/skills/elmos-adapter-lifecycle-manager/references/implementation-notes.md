# Implementation Notes

- Skill ID: `adapter-lifecycle-manager`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 管理 Adapter 训练、依赖、缓存、权限、升级、回滚、撤销和租户归属。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
