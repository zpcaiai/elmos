# Implementation Notes

- Skill ID: `experience-clustering-and-dedupe`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P1`
- Capability: 按任务、语言、框架、失败和修复模式聚类并去除近重复经历。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
