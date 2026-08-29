# Implementation Notes

- Skill ID: `durable-task-checkpoint-memory`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 在暂停、断电、网络中断和进程迁移后恢复任务状态与副作用边界。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
