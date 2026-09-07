# Implementation Notes

- Skill ID: `theorem-prover-integration`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P2`
- Capability: 为关键算法和转换规则生成 Lean/Coq/Isabelle 等证明接口与证据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
