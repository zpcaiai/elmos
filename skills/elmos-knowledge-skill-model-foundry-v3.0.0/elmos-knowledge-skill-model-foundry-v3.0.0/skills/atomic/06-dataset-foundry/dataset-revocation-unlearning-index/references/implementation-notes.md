# Implementation Notes

- Skill ID: `dataset-revocation-unlearning-index`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 记录样本到 Checkpoint/Adapter 的影响范围，支持撤回、删除和选择性重训。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
