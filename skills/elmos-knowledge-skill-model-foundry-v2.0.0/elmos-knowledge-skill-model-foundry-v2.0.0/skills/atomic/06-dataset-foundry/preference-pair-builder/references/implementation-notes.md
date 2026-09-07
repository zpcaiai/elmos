# Implementation Notes

- Skill ID: `preference-pair-builder`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P1`
- Capability: 从人工接受、回滚、修复差异和验证证据生成 chosen/rejected 样本对。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
