# Implementation Notes

- Skill ID: `health-warmup-and-readiness`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 验证权重、Tokenizer、Adapter、依赖、显存和基准请求后才进入流量。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
