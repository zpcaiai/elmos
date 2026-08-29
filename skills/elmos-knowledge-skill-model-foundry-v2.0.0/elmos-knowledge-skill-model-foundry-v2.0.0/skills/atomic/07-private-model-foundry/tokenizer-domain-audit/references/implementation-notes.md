# Implementation Notes

- Skill ID: `tokenizer-domain-audit`
- Pack: `07-private-model-foundry`
- Kernel: `K7 Private Model Foundry`
- Priority: `P1`
- Capability: 分析代码、DSL、标识符、SQL、中文和多语言 Token 效率与分词缺陷。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
