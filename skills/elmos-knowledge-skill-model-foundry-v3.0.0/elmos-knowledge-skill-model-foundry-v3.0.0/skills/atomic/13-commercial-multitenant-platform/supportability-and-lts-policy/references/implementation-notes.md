# Implementation Notes

- Skill ID: `supportability-and-lts-policy`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 定义长期支持版本、补丁、升级路径、停服通知和安全修复承诺。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
