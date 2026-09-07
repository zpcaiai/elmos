# Implementation Notes

- Skill ID: `skill-context-pinning`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 在长任务压缩和子 Agent 委派中保护已激活 Skill 的关键契约。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
