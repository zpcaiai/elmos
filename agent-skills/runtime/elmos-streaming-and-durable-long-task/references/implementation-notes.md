# Implementation Notes

- Skill ID: `streaming-and-durable-long-task`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 支持流式反馈、异步节点、检查点、暂停、恢复、取消和断电恢复。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
