# Implementation Notes

- Skill ID: `dataset-quarantine-management`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 隔离许可证不明、PII、密钥、污染、注入、低质量和结果不确定样本。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
