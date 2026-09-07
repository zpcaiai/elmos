# Implementation Notes

- Skill ID: `ai-ml-bom-and-model-provenance`
- Pack: `11-security-privacy-compliance`
- Kernel: `Cross-Cutting Trust Plane`
- Priority: `P0`
- Capability: 记录模型、数据集、训练方法、框架、Adapter 和部署依赖。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
