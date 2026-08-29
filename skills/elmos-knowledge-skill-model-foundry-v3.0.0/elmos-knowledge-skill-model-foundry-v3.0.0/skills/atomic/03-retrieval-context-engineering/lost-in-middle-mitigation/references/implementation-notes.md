# Implementation Notes

- Skill ID: `lost-in-middle-mitigation`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P1`
- Capability: 通过分段、重排、重复锚点和检索式回读降低长上下文中间信息丢失。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
