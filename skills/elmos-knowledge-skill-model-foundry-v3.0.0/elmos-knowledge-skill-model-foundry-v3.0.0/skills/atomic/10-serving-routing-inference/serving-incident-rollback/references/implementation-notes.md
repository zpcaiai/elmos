# Implementation Notes

- Skill ID: `serving-incident-rollback`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 在泄漏、回归、成本异常或模型失效时自动隔离并恢复已知良好组合。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
