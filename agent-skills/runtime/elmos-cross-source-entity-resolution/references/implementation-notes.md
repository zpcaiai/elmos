# Implementation Notes

- Skill ID: `cross-source-entity-resolution`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 合并文档、代码、数据库、Issue 和运行数据中的同一实体并保留别名。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
