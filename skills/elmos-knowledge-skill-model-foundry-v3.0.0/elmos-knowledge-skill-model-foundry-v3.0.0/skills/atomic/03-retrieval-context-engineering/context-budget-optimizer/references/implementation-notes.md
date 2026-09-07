# Implementation Notes

- Skill ID: `context-budget-optimizer`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 在 Token、延迟和成本约束下最大化有用证据覆盖和相互依赖完整性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
