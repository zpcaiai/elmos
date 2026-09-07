# Implementation Notes

- Skill ID: `semantic-and-ast-deduplication`
- Pack: `06-dataset-foundry`
- Kernel: `K6 Dataset Foundry`
- Priority: `P0`
- Capability: 使用文本、AST、图和行为指纹去除复制、近重复和模板污染。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
