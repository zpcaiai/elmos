# Implementation Notes

- Skill ID: `decision-trace-and-accountability`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 记录谁在何时基于什么证据批准、拒绝、豁免或回滚。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
