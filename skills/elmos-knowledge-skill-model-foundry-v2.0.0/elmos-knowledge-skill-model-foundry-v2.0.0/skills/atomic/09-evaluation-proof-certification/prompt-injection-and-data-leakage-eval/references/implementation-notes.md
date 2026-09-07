# Implementation Notes

- Skill ID: `prompt-injection-and-data-leakage-eval`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 测试直接/间接注入、工具越权、记忆污染、训练数据和跨租户泄漏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
