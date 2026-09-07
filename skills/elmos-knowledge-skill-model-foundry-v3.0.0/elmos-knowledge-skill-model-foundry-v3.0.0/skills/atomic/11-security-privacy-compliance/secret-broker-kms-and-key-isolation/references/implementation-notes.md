# Implementation Notes

- Skill ID: `secret-broker-kms-and-key-isolation`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 不向模型暴露长期密钥，按租户和任务签发短期凭据并轮换。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
