# Implementation Notes

- Skill ID: `tenant-key-and-cache-isolation`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 确保对象、向量、缓存、Adapter、Checkpoint 和备份按租户隔离。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
