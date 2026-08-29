# Implementation Notes

- Skill ID: `hybrid-code-knowledge-retrieval`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 融合关键词、向量、符号、类型和图关系检索代码与知识。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
