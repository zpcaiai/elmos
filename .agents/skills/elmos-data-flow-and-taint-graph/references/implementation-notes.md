# Implementation Notes

- Skill ID: `data-flow-and-taint-graph`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 跟踪变量、字段、对象、请求、数据库和消息中的数据流与污点传播。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
