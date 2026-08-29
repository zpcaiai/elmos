# Implementation Notes

- Skill ID: `dataset-version-card-and-signing`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 冻结版本、生成 Dataset Card、质量报告、权利摘要和数字签名。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
