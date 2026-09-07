# Implementation Notes

- Skill ID: `smt-and-model-checking-adapter`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P1`
- Capability: 把可表达约束交给 SMT、模型检查器或符号执行工具。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
