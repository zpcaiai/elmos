# Implementation Notes

- Skill ID: `tool-trajectory-dataset`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 标准化多轮工具调用、参数、环境反馈和终止状态用于 Agent 训练。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
