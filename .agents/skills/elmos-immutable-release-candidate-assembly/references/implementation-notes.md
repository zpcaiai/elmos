# Implementation Notes

- Skill ID: `immutable-release-candidate-assembly`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P0`
- Capability: 组装模型、Adapter、Skill、知识快照、策略、工具镜像和评测证据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
