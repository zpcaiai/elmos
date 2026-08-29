# Implementation Notes

- Skill ID: `best-of-n-verifier-selection`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 生成多条候选轨迹，通过独立验证器选择或融合最可靠方案。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
