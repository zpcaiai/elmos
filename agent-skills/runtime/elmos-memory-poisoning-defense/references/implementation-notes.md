# Implementation Notes

- Skill ID: `memory-poisoning-defense`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 检测恶意、错误或低置信记忆，阻止其进入规划、检索与训练。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
