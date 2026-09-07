# Implementation Notes

- Skill ID: `repository-incremental-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 按提交、分支和文件增量摄取仓库，保留删除、重命名、子模块和生成代码语义。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
