# Implementation Notes

- Skill ID: `symbol-aware-retrieval`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 围绕定义、引用、实现、测试、配置和调用方检索完整符号上下文。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
