# Implementation Notes

- Skill ID: `annotation-and-comparison-workbench`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 支持轨迹、补丁、证据、偏好对和失败类型的高效标注。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
