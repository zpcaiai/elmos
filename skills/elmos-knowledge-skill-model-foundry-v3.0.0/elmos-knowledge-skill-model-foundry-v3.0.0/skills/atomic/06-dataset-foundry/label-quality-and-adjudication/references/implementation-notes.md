# Implementation Notes

- Skill ID: `label-quality-and-adjudication`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 测量标注一致性、证据覆盖和审阅偏差，并执行专家仲裁。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
