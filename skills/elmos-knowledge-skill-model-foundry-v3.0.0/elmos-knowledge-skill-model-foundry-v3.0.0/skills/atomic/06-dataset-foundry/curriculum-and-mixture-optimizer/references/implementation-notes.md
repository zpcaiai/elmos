# Implementation Notes

- Skill ID: `curriculum-and-mixture-optimizer`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 按难度、语言、业务线和失败模式优化训练顺序与数据混合比例。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
