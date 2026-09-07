# Implementation Notes

- Skill ID: `hard-negative-data-mining`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 挖掘看似合理但版本、类型、事务、安全或行为错误的负例。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
