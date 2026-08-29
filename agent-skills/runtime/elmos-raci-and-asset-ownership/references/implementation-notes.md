# Implementation Notes

- Skill ID: `raci-and-asset-ownership`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 为知识、Skill、数据集、模型、策略、发布和事件明确 RACI。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
