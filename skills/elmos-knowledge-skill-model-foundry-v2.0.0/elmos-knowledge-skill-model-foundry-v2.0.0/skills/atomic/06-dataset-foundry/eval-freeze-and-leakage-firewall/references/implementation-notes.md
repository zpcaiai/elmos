# Implementation Notes

- Skill ID: `eval-freeze-and-leakage-firewall`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 冻结评测集并在数据流水线、检索、Prompt 和训练阶段阻断泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
