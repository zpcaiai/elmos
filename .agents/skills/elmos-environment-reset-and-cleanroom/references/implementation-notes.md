# Implementation Notes

- Skill ID: `environment-reset-and-cleanroom`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 确保每次 Rollout 从已知状态开始，并检测跨任务状态和答案泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
