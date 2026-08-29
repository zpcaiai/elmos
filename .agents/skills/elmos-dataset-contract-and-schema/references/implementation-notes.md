# Implementation Notes

- Skill ID: `dataset-contract-and-schema`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 定义任务、上下文、轨迹、补丁、证据、奖励、权限和血缘的标准训练样本结构。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
