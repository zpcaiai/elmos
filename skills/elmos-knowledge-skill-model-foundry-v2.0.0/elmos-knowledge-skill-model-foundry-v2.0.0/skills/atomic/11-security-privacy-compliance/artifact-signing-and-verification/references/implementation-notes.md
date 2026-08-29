# Implementation Notes

- Skill ID: `artifact-signing-and-verification`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 对 Skill、模型、Adapter、数据集、镜像和证据签名并在使用前验证。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
