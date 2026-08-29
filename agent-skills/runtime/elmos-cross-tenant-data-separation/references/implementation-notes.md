# Implementation Notes

- Skill ID: `cross-tenant-data-separation`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 通过物理或逻辑分区、密钥和查询策略阻止跨租户训练泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
