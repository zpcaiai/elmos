# Implementation Notes

- Skill ID: `security-regression-certification`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 验证权限不扩大、输入处理、依赖、秘密、注入和供应链安全。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
