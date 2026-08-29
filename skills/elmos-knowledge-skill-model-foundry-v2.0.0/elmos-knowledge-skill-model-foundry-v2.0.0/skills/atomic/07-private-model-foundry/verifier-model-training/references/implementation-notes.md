# Implementation Notes

- Skill ID: `verifier-model-training`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 训练补丁风险、行为等价、测试缺口、幻觉 API 和上线可接受性判断。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
