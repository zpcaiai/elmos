# Implementation Notes

- Skill ID: `working-memory-manager`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 维护当前任务假设、计划、约束、待办、已验证事实和风险，不混入长期记忆。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
