# Implementation Notes

- Skill ID: `archive-and-folder-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 安全处理文件夹、zip、tar.gz、嵌套归档、超大文件和损坏归档。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
