# Implementation Notes

- Skill ID: `sql-ddl-dml-constraint-conversion`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 转换表、索引、约束、分区、序列、Identity、MERGE 和 Upsert。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
