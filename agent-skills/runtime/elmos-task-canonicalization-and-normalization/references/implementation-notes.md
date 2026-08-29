# Implementation Notes

- Skill ID: `task-canonicalization-and-normalization`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 统一需求、错误、环境、期望结果和验收条件，减少标签噪声。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
