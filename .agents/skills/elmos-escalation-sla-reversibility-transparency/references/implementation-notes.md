# Implementation Notes

- Skill ID: `escalation-sla-reversibility-transparency`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 定义升级时限、人工接管、撤销路径和对用户透明的信息。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
