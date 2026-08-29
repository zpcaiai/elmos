# Implementation Notes

- Skill ID: `tool-selection-and-argument-policy`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 分别优化工具选择与参数生成，并以 Schema 和权限进行动作约束。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
