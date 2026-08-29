# Implementation Notes

- Skill ID: `stale-and-conflict-arbitration`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P0`
- Capability: 识别过期或冲突上下文，按权威度、时间和运行证据裁决。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
