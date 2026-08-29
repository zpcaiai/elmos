# Implementation Notes

- Skill ID: `chaos-soak-backup-restore-certification`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P0`
- Capability: 验证长稳、故障注入、备份、恢复、跨区和依赖失效。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
