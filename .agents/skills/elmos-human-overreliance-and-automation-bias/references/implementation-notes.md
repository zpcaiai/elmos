# Implementation Notes

- Skill ID: `human-overreliance-and-automation-bias`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P1`
- Capability: 通过界面、抽检和培训降低对模型分数和自动证据的盲从。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
