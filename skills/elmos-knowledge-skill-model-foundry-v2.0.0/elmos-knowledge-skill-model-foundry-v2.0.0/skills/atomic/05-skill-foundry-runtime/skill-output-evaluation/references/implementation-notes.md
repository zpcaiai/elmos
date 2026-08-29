# Implementation Notes

- Skill ID: `skill-output-evaluation`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 检查最终代码、文档、补丁、报告和证据是否满足契约。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
