# Implementation Notes

- Skill ID: `ingestion-quarantine-gate`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 对来源不明、许可不清、解析失败、污染或恶意内容执行隔离与复核。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
