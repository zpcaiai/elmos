# Implementation Notes

- Skill ID: `gold-certified-promotion`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 要求独立验证、完整证据、专家接受或跨仓库复现后进入高可信训练层。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
