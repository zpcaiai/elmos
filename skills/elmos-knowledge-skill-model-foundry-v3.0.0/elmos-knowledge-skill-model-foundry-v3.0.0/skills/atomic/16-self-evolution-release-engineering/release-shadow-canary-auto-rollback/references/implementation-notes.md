# Implementation Notes

- Skill ID: `release-shadow-canary-auto-rollback`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P0`
- Capability: 根据硬门和实时 SLO 自动暂停、回滚或扩大流量。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
