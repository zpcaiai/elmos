# Implementation Notes

- Skill ID: `contract-migration-manager`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P1`
- Capability: 在契约 Schema 升级时完成向前兼容、双写、迁移验证和安全回滚。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
