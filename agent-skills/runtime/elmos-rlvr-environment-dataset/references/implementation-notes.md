# Implementation Notes

- Skill ID: `rlvr-environment-dataset`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 把仓库、任务、镜像、测试、奖励和终止条件封装为可复现 RL 环境。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
