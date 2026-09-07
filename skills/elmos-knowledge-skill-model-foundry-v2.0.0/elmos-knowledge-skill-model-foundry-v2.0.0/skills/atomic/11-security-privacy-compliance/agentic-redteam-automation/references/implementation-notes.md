# Implementation Notes

- Skill ID: `agentic-redteam-automation`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 覆盖目标劫持、工具滥用、权限滥用、记忆污染、级联失败和 Rogue Agent。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
