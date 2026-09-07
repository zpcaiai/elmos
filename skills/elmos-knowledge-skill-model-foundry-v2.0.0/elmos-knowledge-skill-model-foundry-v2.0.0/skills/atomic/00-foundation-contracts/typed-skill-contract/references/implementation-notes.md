# Implementation Notes

- Skill ID: `typed-skill-contract`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 定义 Skill 的输入、输出、前置条件、后置条件、工具权限、失败语义和副作用契约。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
