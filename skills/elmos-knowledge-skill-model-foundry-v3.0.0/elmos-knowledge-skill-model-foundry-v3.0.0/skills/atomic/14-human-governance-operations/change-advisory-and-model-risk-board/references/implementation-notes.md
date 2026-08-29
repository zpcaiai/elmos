# Implementation Notes

- Skill ID: `change-advisory-and-model-risk-board`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P1`
- Capability: 对高风险模型、训练和生产变更执行跨职能评审。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
