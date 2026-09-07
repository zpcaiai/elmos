# Implementation Notes

- Skill ID: `workspace-attachment-ownership-fencing`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 为远程 Executor、Workspace、挂载和产物建立所有权与 Fencing Token。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
