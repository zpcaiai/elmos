# Implementation Notes

- Skill ID: `base-model-selection-and-license`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P0`
- Capability: 根据代码能力、上下文、工具使用、许可证、硬件和私有部署需求选择基座。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
