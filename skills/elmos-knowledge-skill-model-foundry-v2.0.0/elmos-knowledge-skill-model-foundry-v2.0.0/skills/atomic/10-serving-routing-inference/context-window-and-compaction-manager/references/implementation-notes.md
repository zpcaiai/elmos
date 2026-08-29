# Implementation Notes

- Skill ID: `context-window-and-compaction-manager`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 管理上下文预算、压缩、恢复锚点和 Skill/证据保护。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
