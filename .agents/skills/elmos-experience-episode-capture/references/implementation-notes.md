# Implementation Notes

- Skill ID: `experience-episode-capture`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P0`
- Capability: 形成标准 Episode，绑定仓库快照、知识、Skill、模型、环境和最终验收。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
