# Implementation Notes

- Skill ID: `sql-dialect-parser-and-semantic-ir`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 解析多数据库 SQL、PL/SQL、T-SQL、PL/pgSQL 和扩展语法。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
