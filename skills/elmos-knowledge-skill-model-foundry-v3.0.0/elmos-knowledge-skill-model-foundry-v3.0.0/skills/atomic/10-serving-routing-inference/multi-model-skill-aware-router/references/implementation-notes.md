# Implementation Notes

- Skill ID: `multi-model-skill-aware-router`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 根据任务、Skill、语言、风险、上下文和历史表现选择模型组合。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
