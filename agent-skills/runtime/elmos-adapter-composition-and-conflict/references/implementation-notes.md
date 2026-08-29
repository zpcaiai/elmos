# Implementation Notes

- Skill ID: `adapter-composition-and-conflict`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 评估多 Adapter 组合、路由、加权、合并和能力冲突。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
