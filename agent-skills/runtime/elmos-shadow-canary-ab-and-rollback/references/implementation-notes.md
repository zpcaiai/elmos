# Implementation Notes

- Skill ID: `shadow-canary-ab-and-rollback`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 执行影子、流量拆分、自动门控和发布组合整体回滚。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
