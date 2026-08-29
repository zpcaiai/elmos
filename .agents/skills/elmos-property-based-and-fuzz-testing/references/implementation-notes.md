# Implementation Notes

- Skill ID: `property-based-and-fuzz-testing`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P1`
- Capability: 从类型、约束和协议生成边界、随机与恶意输入。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
