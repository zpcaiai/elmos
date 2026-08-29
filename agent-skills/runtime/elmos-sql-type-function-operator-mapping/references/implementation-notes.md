# Implementation Notes

- Skill ID: `sql-type-function-operator-mapping`
- Pack: `15-domain-engineering-packs`
- Kernel: `Domain Packs over K1-K8`
- Priority: `P0`
- Capability: 映射类型、隐式转换、函数、运算符、Collation、时区和 Null。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
