# Implementation Notes

- Skill ID: `sft-dataset-builder`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 构建包含任务、上下文、计划、工具、补丁和验证结果的监督微调数据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
