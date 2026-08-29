# Implementation Notes

- Skill ID: `task-specific-reranking`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 按任务类型训练并应用代码、文档、错误和 Skill 专用重排器。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
