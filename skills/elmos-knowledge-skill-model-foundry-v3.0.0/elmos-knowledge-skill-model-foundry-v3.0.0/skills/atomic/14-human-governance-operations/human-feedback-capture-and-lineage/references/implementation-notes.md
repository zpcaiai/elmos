# Implementation Notes

- Skill ID: `human-feedback-capture-and-lineage`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 记录反馈来源、范围、版本、意图、置信度和后续使用。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
