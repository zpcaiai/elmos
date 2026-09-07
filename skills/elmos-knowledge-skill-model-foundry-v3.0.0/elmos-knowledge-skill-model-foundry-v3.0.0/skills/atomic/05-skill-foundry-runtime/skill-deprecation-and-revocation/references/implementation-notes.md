# Implementation Notes

- Skill ID: `skill-deprecation-and-revocation`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 在缺陷、安全事件或依赖失效时阻止新调用并迁移现有任务。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
