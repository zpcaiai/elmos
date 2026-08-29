# Implementation Notes

- Skill ID: `semantic-diff-and-impact-analysis`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 比较两个版本的 API、行为、数据、依赖和风险变化，而非仅文本差异。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
