# Implementation Notes

- Skill ID: `data-usage-consent-contract`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 约束数据可否检索、记录、标注、训练、跨租户聚合、导出、删除和保留。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
