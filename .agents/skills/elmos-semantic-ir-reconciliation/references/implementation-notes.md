# Implementation Notes

- Skill ID: `semantic-ir-reconciliation`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P0`
- Capability: 将多解析器、多语言和多来源结果收敛为可追溯、带置信度的统一 Semantic IR。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
