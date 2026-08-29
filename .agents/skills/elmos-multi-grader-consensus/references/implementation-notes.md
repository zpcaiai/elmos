# Implementation Notes

- Skill ID: `multi-grader-consensus`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P1`
- Capability: 对高风险结论使用多模型、规则和人工共识，保留分歧。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
