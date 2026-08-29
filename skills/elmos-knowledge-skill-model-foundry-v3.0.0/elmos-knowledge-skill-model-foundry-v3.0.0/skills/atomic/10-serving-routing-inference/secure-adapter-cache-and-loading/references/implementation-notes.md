# Implementation Notes

- Skill ID: `secure-adapter-cache-and-loading`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 验证签名、来源、租户和哈希后加载 Adapter，并隔离缓存。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
