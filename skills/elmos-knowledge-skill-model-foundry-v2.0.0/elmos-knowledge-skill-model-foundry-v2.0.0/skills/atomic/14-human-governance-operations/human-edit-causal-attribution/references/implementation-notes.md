# Implementation Notes

- Skill ID: `human-edit-causal-attribution`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P1`
- Capability: 判断人工修改是修错、补需求、偏好、环境差异还是格式调整。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
