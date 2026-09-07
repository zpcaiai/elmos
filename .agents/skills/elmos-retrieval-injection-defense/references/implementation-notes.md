# Implementation Notes

- Skill ID: `retrieval-injection-defense`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 隔离不可信内容、标记指令性文本并阻止知识内容升级为系统权限。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
