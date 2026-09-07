# Implementation Notes

- Skill ID: `cross-agent-skill-portability`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 验证 Skill 在 Codex、Claude Code、兼容 Agent 和 Elmos Runtime 的可移植性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
