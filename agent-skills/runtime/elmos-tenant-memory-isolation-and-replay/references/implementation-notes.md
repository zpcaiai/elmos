# Implementation Notes

- Skill ID: `tenant-memory-isolation-and-replay`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 确保经验不可跨租户泄漏，且在固定环境中可以确定性重放验证。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
