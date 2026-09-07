# Implementation Notes

- Skill ID: `direct-indirect-prompt-injection-defense`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 区分数据与指令，标记来源、降低权限并验证高风险操作意图。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
