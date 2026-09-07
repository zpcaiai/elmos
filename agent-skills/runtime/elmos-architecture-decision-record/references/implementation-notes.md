# Implementation Notes

- Skill ID: `architecture-decision-record`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P1`
- Capability: 把关键架构选择、假设、替代方案和退出条件沉淀为可检索 ADR。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
