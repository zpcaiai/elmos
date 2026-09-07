# Implementation Notes

- Skill ID: `dataset-lineage-and-provenance`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 记录每个样本来自哪些对象、任务、模型、Skill、人工修改和转换步骤。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
