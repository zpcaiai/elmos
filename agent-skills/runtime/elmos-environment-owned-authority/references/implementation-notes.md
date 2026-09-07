# Implementation Notes

- Skill ID: `environment-owned-authority`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 权限归属于实际执行环境而非 Thread 全局状态，恢复后仍保持原始边界。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
