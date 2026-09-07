# Implementation Notes

- Skill ID: `complexity-risk-cost-latency-routing`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 在质量、风险、成本和延迟的 Pareto 约束下动态路由。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
