# Implementation Notes

- Skill ID: `privacy-preserving-federated-learning`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P1`
- Capability: 为联邦 Adapter 学习增加安全聚合、更新裁剪和异常客户端检测。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
