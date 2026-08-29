# Implementation Notes

- Skill ID: `release-bundle-contract`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 把模型、Adapter、Skill 集、知识快照、工具链、策略和评测基线绑定为不可变发布单元。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
