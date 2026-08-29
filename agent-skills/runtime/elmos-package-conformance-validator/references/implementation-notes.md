# Implementation Notes

- Skill ID: `package-conformance-validator`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 对整个 Skills Package 执行结构、命名、权限、证据和依赖一致性校验。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
