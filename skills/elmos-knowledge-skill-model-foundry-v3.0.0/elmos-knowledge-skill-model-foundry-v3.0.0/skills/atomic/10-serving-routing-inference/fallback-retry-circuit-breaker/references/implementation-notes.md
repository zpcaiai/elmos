# Implementation Notes

- Skill ID: `fallback-retry-circuit-breaker`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 区分可重试、不可重试和副作用操作，执行退避、降级与熔断。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
