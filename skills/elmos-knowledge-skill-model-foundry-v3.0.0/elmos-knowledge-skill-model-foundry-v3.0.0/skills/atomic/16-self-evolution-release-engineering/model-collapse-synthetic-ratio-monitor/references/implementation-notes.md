# Implementation Notes

- Skill ID: `model-collapse-synthetic-ratio-monitor`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 监控合成数据占比、分布收缩、错误放大和多样性丢失。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
