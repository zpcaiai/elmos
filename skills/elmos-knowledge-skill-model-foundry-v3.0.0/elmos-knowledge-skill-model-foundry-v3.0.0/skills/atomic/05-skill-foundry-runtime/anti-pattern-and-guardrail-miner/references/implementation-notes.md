# Implementation Notes

- Skill ID: `anti-pattern-and-guardrail-miner`
- Pack: `05-skill-foundry-runtime`
- Kernel: `K5 Skill Foundry and Runtime`
- Priority: `P1`
- Capability: 把重复错误、绕过行为和风险操作沉淀为禁止规则与防护 Skill。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
