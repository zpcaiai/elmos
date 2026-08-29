# Implementation Notes

- Skill ID: `training-rights-enforcement`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 在数据读取、混合、训练、导出和发布阶段持续执行许可与合同限制。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
