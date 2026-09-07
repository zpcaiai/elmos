# Implementation Notes

- Skill ID: `model-provider-abstraction`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 隔离 OpenAI、Anthropic、开源模型、私有服务和未来推理引擎差异。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
