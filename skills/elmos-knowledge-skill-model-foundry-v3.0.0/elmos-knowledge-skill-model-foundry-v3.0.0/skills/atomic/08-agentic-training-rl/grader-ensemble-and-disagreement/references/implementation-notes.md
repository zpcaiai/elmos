# Implementation Notes

- Skill ID: `grader-ensemble-and-disagreement`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 融合确定性检查、多个 Verifier 和人工标签，并利用分歧发现薄弱样本。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
