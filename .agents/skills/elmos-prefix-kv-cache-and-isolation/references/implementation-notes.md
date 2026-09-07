# Implementation Notes

- Skill ID: `prefix-kv-cache-and-isolation`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P1`
- Capability: 利用 Prefix/KV Cache 降低成本，同时防止租户和权限上下文串用。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
