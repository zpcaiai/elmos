# Implementation Notes

- Skill ID: `trajectory-to-skill-miner`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 从多次成功且已验证轨迹中抽取稳定步骤、参数和适用边界。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
