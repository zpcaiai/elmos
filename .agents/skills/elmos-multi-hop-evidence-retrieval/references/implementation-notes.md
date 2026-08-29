# Implementation Notes

- Skill ID: `multi-hop-evidence-retrieval`
- Pack: `03-retrieval-context-engineering`
- Kernel: `K3 Retrieval and Context Kernel`
- Priority: `P1`
- Capability: 通过多跳图搜索补齐需求到实现、实现到测试、错误到修复的链路。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
