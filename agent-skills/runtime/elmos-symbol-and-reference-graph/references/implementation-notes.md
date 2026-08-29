# Implementation Notes

- Skill ID: `symbol-and-reference-graph`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 解析定义、引用、重载、泛型、反射、动态调用和跨模块符号关系。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
