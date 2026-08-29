# Implementation Notes

- Skill ID: `database-metadata-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 摄取 Schema、Routine、触发器、索引、约束、统计信息和执行计划。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
