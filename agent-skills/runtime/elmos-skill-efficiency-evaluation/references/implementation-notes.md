# Implementation Notes

- Skill ID: `skill-efficiency-evaluation`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 衡量 Token、工具次数、重试、Wall-clock、缓存和成本效率。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
