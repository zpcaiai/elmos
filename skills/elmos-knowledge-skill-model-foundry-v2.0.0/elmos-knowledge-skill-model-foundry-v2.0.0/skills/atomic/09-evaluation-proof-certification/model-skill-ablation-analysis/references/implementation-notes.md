# Implementation Notes

- Skill ID: `model-skill-ablation-analysis`
- Pack: `09-evaluation-proof-certification`
- Kernel: `K8 Formal Assurance and Evidence`
- Priority: `P0`
- Capability: 分离模型、Skill、检索、工具和训练改动对结果的贡献。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
