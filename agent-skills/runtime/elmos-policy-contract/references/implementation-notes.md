# Implementation Notes

- Skill ID: `policy-contract`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 把数据、权限、训练、部署和合规规则表达成可执行、可测试、可审计的策略契约。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
