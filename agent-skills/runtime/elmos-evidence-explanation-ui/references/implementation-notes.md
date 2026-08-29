# Implementation Notes

- Skill ID: `evidence-explanation-ui`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 以代码位置、差分、测试、反例、风险和来源展示结论。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
