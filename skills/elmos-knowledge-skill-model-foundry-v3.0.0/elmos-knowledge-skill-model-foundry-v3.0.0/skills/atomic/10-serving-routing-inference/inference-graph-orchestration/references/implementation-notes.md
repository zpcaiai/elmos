# Implementation Notes

- Skill ID: `inference-graph-orchestration`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P1`
- Capability: 支持 Router、Sequence、Ensemble、Verifier 和 Fallback 的推理图。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
