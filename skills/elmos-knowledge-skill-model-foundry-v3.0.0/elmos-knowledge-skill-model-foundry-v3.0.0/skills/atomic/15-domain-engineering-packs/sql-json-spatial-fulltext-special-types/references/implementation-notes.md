# Implementation Notes

- Skill ID: `sql-json-spatial-fulltext-special-types`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P1`
- Capability: 转换 JSON、数组、空间、全文、XML 和厂商专有类型。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
