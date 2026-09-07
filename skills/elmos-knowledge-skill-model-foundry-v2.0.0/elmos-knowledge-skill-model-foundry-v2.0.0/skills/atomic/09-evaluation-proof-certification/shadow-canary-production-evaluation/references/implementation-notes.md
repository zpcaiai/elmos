# Implementation Notes

- Skill ID: `shadow-canary-production-evaluation`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 在影子和金丝雀流量中对比质量、成本、失败和回滚信号。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
