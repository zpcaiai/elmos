# Implementation Notes

- Skill ID: `dense-partial-credit-reward`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 使用测试子集、覆盖、编译进度和不变量满足度提供稠密奖励。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
