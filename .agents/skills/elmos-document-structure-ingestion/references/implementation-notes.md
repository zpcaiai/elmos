# Implementation Notes

- Skill ID: `document-structure-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 解析 Markdown、HTML、Word、PDF、TXT 与表格，恢复标题、章节、表格、引用和附件关系。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
