# Implementation Notes

- Skill ID: `process-supervision-dataset`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 构造步骤级正确性、工具选择、检查点和错误恢复标签。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
