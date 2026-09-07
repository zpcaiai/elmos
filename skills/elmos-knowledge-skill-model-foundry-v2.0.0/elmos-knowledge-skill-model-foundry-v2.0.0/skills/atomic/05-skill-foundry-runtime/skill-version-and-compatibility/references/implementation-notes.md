# Implementation Notes

- Skill ID: `skill-version-and-compatibility`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 管理 SemVer、兼容范围、依赖锁定、升级迁移和回滚版本。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
