# Implementation Notes

- Skill ID: `automatic-curriculum-and-benchmark-builder`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P2`
- Capability: 从真实失败生成分层课程和无泄漏的新基准。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
