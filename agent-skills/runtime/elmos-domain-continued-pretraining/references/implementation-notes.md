# Implementation Notes

- Skill ID: `domain-continued-pretraining`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P2`
- Capability: 对稳定、授权、规模足够的领域语料执行 CPT，并监测能力迁移和遗忘。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
