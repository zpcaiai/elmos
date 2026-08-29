# Implementation Notes

- Skill ID: `human-edit-diff-analysis`
- Pack: `04-memory-experience-flywheel`
- Kernel: `K4 Memory and Experience Kernel`
- Priority: `P1`
- Capability: 区分人工对模型结果的修错、偏好调整、补需求和无关格式修改。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
