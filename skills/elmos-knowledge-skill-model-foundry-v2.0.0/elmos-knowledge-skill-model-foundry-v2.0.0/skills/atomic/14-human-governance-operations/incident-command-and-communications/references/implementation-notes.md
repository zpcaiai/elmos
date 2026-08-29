# Implementation Notes

- Skill ID: `incident-command-and-communications`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 明确事件指挥、技术处置、客户沟通、法律和复盘职责。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
