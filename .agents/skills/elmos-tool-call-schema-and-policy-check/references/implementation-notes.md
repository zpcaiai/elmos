# Implementation Notes

- Skill ID: `tool-call-schema-and-policy-check`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 在执行前验证工具名、参数、权限、审批和幂等键。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
