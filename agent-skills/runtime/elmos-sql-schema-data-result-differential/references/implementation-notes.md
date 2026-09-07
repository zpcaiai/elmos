# Implementation Notes

- Skill ID: `sql-schema-data-result-differential`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 比较 Schema、数据、结果集、顺序、精度、副作用和错误。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
