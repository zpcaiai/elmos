# Implementation Notes

- Skill ID: `bronze-dataset-intake`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 保存原始轨迹和产物但禁止训练，确保可追溯和可重新处理。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
