# Implementation Notes

- Skill ID: `recertification-trigger-engine`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P0`
- Capability: 在模型、数据、知识、Skill、工具、法规或环境变化时触发相应复认证。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
