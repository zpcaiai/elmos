# Implementation Notes

- Skill ID: `self-correction-with-independent-verifier`
- Pack: `16-self-evolution-release-engineering`
- Kernel: `Learning Flywheel and Release Kernel`
- Priority: `P1`
- Capability: 允许自动修复，但由独立验证器和发布门决定是否接受。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
