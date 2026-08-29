# Implementation Notes

- Skill ID: `private-airgap-deployment-packager`
- Pack: `13-commercial-multitenant-platform`
- Kernel: `Commercial Control Plane`
- Priority: `P0`
- Capability: 生成镜像、模型、Skill、知识、许可证、更新、备份和 Runbook 离线包。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
