# Implementation Notes

- Skill ID: `tenant-adapter-resolver`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 只解析当前租户授权且与基座、任务和版本兼容的 Adapter。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
