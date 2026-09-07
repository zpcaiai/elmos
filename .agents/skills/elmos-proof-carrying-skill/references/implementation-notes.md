# Implementation Notes

- Skill ID: `proof-carrying-skill`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 要求 Skill 输出可机器验证的证明义务、测试结果、未决风险和回滚信息。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
