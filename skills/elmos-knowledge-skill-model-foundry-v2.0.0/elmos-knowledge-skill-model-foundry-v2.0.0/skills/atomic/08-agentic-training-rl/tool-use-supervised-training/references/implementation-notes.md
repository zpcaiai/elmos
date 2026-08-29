# Implementation Notes

- Skill ID: `tool-use-supervised-training`
- Pack: `08-agentic-training-rl`
- Kernel: `K7 Private Model Foundry / Agent Learning`
- Priority: `P1`
- Capability: 训练何时读取、搜索、编辑、编译、测试、查询和请求审批。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
