# Implementation Notes

- Skill ID: `lifelong-learning-and-forgetting-control`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P2`
- Capability: 联合管理持续学习、回放、遗忘、数据撤回和能力稳定性。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
