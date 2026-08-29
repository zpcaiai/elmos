# Implementation Notes

- Skill ID: `multi-teacher-distillation`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 从多个强模型和工具验证结果蒸馏稳定能力，减少单一教师偏差。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
