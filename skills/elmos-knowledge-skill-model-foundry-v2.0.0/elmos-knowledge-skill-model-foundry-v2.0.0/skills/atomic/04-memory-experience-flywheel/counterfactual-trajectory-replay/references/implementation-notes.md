# Implementation Notes

- Skill ID: `counterfactual-trajectory-replay`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P2`
- Capability: 替换关键决策或上下文重放轨迹，估计某项改动的真实贡献。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
