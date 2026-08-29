# Implementation Notes

- Skill ID: `china-ai-data-compliance-profile`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 维护中国网络、数据、个人信息、生成式 AI 备案/登记和标识要求映射。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
