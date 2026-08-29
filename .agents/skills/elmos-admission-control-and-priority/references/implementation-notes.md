# Implementation Notes

- Skill ID: `admission-control-and-priority`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 按并发上限、账户余额、任务优先级、GPU 和截止时间控制入场。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
