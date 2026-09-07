# Implementation Notes

- Skill ID: `skill-robustness-evaluation`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 覆盖边界输入、版本变化、工具失败、并发、恢复和恶意内容。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
