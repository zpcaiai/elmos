# Implementation Notes

- Skill ID: `catastrophic-forgetting-detection`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 在每次训练后按语言、业务线、工具、长任务和安全集检测遗忘。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
