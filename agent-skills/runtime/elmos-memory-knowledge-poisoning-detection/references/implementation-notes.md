# Implementation Notes

- Skill ID: `memory-knowledge-poisoning-detection`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 识别恶意知识、持久化指令、错误高置信记录和跨任务污染。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
