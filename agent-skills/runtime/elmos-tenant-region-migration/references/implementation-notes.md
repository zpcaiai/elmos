# Implementation Notes

- Skill ID: `tenant-region-migration`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P1`
- Capability: 在保持身份、加密、血缘和停机目标下迁移区域或私有环境。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
