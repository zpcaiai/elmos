# Implementation Notes

- Skill ID: `gpu-scheduling-and-autoscaling`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 根据模型、上下文、Adapter、显存、队列和 SLA 调度 GPU。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
