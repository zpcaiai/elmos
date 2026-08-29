# Implementation Notes

- Skill ID: `weight-to-skill-extraction`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P2`
- Capability: 从模型稳定行为中提取可解释、可测试的显式 Skill。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
