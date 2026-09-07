# Implementation Notes

- Skill ID: `least-privilege-tool-authorization`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 按任务、Environment、Attachment 和 Skill 精确授予工具与参数权限。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
