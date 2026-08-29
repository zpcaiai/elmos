# Implementation Notes

- Skill ID: `automated-process-supervision`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 利用规则、验证器和搜索生成步骤级正负反馈。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
