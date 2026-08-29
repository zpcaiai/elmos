# Implementation Notes

- Skill ID: `sql-plan-performance-certification`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 比较执行计划、索引、统计、锁和性能，阻止语义正确但不可用的转换。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
