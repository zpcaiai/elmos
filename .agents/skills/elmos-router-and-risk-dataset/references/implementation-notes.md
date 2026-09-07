# Implementation Notes

- Skill ID: `router-and-risk-dataset`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 构建任务分类、Skill/模型选择、复杂度、风险和人工审批标签。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
