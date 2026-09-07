# Implementation Notes

- Skill ID: `skill-to-weight-distillation`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P2`
- Capability: 将高频、稳定、跨仓库 Skill 轨迹蒸馏进模型并保留原 Skill 作为校验。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
