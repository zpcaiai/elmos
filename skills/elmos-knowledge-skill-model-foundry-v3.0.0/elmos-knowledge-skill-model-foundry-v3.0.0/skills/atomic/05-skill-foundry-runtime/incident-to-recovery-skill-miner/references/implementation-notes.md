# Implementation Notes

- Skill ID: `incident-to-recovery-skill-miner`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 从故障与恢复记录生成诊断、止损、修复和复盘 Skill。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
