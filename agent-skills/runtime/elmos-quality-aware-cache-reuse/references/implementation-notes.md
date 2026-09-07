# Implementation Notes

- Skill ID: `quality-aware-cache-reuse`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P1`
- Capability: 仅在任务语义、权限、版本和证据相容时复用响应或中间结果。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
