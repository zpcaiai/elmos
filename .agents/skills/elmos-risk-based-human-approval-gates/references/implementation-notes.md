# Implementation Notes

- Skill ID: `risk-based-human-approval-gates`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 根据副作用、客户级别、证据缺口和不确定性决定人工门。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
