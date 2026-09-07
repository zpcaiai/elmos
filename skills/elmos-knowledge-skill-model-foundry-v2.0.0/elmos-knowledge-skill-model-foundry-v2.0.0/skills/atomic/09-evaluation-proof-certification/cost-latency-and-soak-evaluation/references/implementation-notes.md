# Implementation Notes

- Skill ID: `cost-latency-and-soak-evaluation`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 评估长任务 Wall-clock、Token、工具成本、并发、稳定性和资源泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
