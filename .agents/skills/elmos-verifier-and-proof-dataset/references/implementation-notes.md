# Implementation Notes

- Skill ID: `verifier-and-proof-dataset`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 构建补丁正确性、测试充分性、行为等价和证据缺口训练数据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
