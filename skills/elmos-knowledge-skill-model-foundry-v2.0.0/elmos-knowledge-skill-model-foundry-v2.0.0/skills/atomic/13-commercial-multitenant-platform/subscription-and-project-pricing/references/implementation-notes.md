# Implementation Notes

- Skill ID: `subscription-and-project-pricing`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 支持订阅、Usage Credit、按项目、按仓库规模和混合计费。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
