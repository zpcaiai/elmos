# Implementation Notes

- Skill ID: `usage-metering-and-slo`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 记录 Token、缓存、GPU、工具、延迟、错误和可用性并计算 SLA。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
