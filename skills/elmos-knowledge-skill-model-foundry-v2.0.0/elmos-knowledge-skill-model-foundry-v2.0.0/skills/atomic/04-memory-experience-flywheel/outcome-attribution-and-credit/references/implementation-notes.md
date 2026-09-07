# Implementation Notes

- Skill ID: `outcome-attribution-and-credit`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P1`
- Capability: 把最终成功或失败归因到检索、Skill、计划、工具、模型和验证步骤。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
