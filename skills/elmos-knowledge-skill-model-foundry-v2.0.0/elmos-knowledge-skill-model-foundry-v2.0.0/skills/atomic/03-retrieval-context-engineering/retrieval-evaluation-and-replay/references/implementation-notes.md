# Implementation Notes

- Skill ID: `retrieval-evaluation-and-replay`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 离线重放检索过程并计算 Recall、MRR、引用准确率和有用上下文比。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
