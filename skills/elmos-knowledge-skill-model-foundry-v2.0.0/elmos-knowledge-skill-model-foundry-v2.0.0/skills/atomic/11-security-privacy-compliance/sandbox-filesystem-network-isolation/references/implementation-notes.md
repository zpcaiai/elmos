# Implementation Notes

- Skill ID: `sandbox-filesystem-network-isolation`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 限制文件路径、系统调用、进程、设备、网络出口、DNS 和凭据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
