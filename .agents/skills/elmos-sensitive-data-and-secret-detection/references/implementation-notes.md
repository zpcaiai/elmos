# Implementation Notes

- Skill ID: `sensitive-data-and-secret-detection`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P0`
- Capability: 发现凭据、密钥、个人信息、商业秘密、受监管数据和高敏代码。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
