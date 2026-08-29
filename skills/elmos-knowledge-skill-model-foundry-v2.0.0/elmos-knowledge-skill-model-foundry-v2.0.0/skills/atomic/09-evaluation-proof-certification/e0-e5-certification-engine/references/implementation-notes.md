# Implementation Notes

- Skill ID: `e0-e5-certification-engine`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 把来源、单测、集成、影子、金丝雀和长期运行证据映射为 E0-E5。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
