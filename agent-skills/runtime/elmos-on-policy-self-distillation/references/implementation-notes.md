# Implementation Notes

- Skill ID: `on-policy-self-distillation`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 从模型自身经验证的成功与失败轨迹中进行受控自蒸馏。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
