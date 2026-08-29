# Implementation Notes

- Skill ID: `secret-pii-and-sensitive-redaction`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 对代码、日志、Prompt、工具结果和补丁执行可验证脱敏并保留替换映射权限。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
