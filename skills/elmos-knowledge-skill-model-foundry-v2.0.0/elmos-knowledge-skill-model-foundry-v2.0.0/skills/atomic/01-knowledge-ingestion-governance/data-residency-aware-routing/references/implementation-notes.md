# Implementation Notes

- Skill ID: `data-residency-aware-routing`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P1`
- Capability: 按租户、地域和法规要求选择存储、索引、处理和训练区域。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
