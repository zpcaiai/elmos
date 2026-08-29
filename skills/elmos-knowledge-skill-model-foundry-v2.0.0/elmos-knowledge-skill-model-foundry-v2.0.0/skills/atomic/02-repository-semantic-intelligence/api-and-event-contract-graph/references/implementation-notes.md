# Implementation Notes

- Skill ID: `api-and-event-contract-graph`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 建立 API、RPC、事件、Schema、消费者和生产者的契约依赖图。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
