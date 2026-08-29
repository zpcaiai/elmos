# Implementation Notes

- Skill ID: `skill-activation-router`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 根据用户意图、仓库事实、风险和能力置信度选择应加载的 Skill。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
