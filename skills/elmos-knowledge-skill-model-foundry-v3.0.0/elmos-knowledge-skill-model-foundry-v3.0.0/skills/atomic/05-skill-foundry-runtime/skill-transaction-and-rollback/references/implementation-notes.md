# Implementation Notes

- Skill ID: `skill-transaction-and-rollback`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P0`
- Capability: 为有副作用 Skill 建立幂等键、补偿事务、检查点和回滚演练。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
