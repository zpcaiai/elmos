# Implementation Notes

- Skill ID: `repo-org-time-split-builder`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 按仓库、组织、时间、家族和 Fork 分组切分，避免相似提交跨训练与测试。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
