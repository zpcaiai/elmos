# Implementation Notes

- Skill ID: `hierarchical-skill-registry`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 提供平台、组织、租户、项目和仓库级 Skill 注册、搜索和优先级覆盖。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
