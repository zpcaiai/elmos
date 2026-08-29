# Implementation Notes

- Skill ID: `concurrency-correctness-testing`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 检测竞态、死锁、丢失更新、顺序性、可见性和资源泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
