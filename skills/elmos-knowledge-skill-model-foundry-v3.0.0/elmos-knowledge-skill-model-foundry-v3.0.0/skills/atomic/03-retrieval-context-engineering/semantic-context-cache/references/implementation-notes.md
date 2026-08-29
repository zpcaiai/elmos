# Implementation Notes

- Skill ID: `semantic-context-cache`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P1`
- Capability: 缓存任务语义包并根据依赖图和知识变更进行精确失效。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
