# Implementation Notes

- Skill ID: `deprecation-and-obsolescence-detection`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 发现旧文档、旧 API、失效 Skill、弱模型和不再安全的依赖。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
