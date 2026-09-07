# Implementation Notes

- Skill ID: `capability-calibration-and-boundary`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 持续更新模型和 Skill 擅长、薄弱、拒绝和人工升级边界。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
