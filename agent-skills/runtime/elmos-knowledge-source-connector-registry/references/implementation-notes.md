# Implementation Notes

- Skill ID: `knowledge-source-connector-registry`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 注册并治理 Git、对象存储、Wiki、Issue、PR、CI、数据库和日志等知识源连接器。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
