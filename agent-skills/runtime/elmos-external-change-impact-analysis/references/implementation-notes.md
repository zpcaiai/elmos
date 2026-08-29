# Implementation Notes

- Skill ID: `external-change-impact-analysis`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 判断新版本对知识、Skill、模型、评测、部署和客户承诺的影响。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
