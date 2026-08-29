# Implementation Notes

- Skill ID: `security-disaster-recovery`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 验证密钥、Registry、模型、知识、任务状态和审计系统的恢复能力。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
