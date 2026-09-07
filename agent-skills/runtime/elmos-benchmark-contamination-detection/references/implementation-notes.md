# Implementation Notes

- Skill ID: `benchmark-contamination-detection`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 检测公开基准、测试答案、下游评测仓库和相似变体进入训练数据。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
