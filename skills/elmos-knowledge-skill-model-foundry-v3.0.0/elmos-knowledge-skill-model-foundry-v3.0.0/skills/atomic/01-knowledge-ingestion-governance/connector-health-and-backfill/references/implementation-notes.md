# Implementation Notes

- Skill ID: `connector-health-and-backfill`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P1`
- Capability: 监控同步延迟、缺页、断点、权限变化，并安全完成补采与校验。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
