# Implementation Notes

- Skill ID: `query-decomposition-and-rewrite`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P1`
- Capability: 将复合工程任务拆为符号、行为、依赖、测试和风险检索子查询。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
