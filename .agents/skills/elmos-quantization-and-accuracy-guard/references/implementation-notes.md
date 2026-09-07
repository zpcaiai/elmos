# Implementation Notes

- Skill ID: `quantization-and-accuracy-guard`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 执行量化、校准和硬件适配，同时用业务评测阻止精度暗降。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
