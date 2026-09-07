# Implementation Notes

- Skill ID: `edge-and-resource-constrained-serving`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P1`
- Capability: 对小模型、量化、CPU/NPU 和边缘设备进行适配与能力降级。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
