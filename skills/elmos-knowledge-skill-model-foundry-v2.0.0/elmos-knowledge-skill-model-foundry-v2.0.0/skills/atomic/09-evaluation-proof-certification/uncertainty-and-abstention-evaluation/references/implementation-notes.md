# Implementation Notes

- Skill ID: `uncertainty-and-abstention-evaluation`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 评估置信度校准、拒绝率、升级质量和高风险漏报。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
