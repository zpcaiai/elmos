# Implementation Notes

- Skill ID: `continuous-batching-and-speculation`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P1`
- Capability: 优化批处理、Prefill、Decode 和投机解码，并用质量门保护。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
