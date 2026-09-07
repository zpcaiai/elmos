# Implementation Notes

- Skill ID: `procedural-memory-store`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 保存可执行步骤、工具参数、前置条件和回滚方式，为 Skill Mining 提供材料。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
