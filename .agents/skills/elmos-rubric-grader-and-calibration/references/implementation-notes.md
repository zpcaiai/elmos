# Implementation Notes

- Skill ID: `rubric-grader-and-calibration`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P1`
- Capability: 对难以确定性判断的质量维度使用标尺评分并定期校准偏差。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
