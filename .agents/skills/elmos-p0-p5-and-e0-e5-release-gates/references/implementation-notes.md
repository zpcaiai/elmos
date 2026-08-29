# Implementation Notes

- Skill ID: `p0-p5-and-e0-e5-release-gates`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P0`
- Capability: 执行构建、部署、数据、模型、Skill、影子、金丝雀和长期认证门。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
