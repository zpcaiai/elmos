# Implementation Notes

- Skill ID: `model-at-rest-and-in-use-protection`
- Pack: `10-serving-routing-inference`
- Kernel: `K8 Serving and Runtime Control`
- Priority: `P0`
- Capability: 保护模型、Adapter、KV Cache、Prompt 和中间产物的存储与传输。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
