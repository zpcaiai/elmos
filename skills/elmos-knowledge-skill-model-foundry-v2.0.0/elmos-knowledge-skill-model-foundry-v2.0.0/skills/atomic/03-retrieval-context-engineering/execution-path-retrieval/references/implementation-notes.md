# Implementation Notes

- Skill ID: `execution-path-retrieval`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P1`
- Capability: 使用运行 Trace 与失败路径优先选取真实执行相关上下文。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
