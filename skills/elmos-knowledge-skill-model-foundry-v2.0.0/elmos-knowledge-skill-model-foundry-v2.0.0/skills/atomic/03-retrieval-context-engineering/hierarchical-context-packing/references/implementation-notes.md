# Implementation Notes

- Skill ID: `hierarchical-context-packing`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 按架构摘要、文件摘要、符号和必要源码分层组织上下文。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
