# Implementation Notes

- Skill ID: `artifact-identity-and-hashing`
- Pack: `00-foundation-contracts`
- Kernel: `K0 Cross-Kernel Contracts`
- Priority: `P0`
- Capability: 为知识对象、数据集、模型、Adapter、Skill、工具镜像和证据生成不可歧义的内容身份与哈希。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
