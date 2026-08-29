# Implementation Notes

- Skill ID: `deadline-timeout-propagation`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 把任务和节点截止时间贯穿模型、工具、队列和子 Agent。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
