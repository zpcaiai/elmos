# Implementation Notes

- Skill ID: `feedback-manipulation-defense`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 检测恶意评分、刷样本、利益冲突和低质量反馈进入训练。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
