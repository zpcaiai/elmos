# Implementation Notes

- Skill ID: `sql-routine-control-dynamic-conversion`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 转换过程、函数、包、游标、控制流、动态 SQL 和临时对象。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
