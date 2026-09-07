# Implementation Notes

- Skill ID: `skill-authoring-workbench`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 从需求和领域方法创建兼容 SKILL.md 的强类型 Skill，并生成模板、契约和评测。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
