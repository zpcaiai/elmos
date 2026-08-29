# Implementation Notes

- Skill ID: `tenant-adapter-commercial-lifecycle`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P1`
- Capability: 管理租户 Adapter 的训练授权、成本、部署、升级、归属和退出。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
