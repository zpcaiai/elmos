# Implementation Notes

- Skill ID: `pause-resume-cancel-idempotency-training`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P0`
- Capability: 让 Agent 在中断和重复请求下保持状态一致、无重复副作用。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
