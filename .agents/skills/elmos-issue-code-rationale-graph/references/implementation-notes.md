# Implementation Notes

- Skill ID: `issue-code-rationale-graph`
- Pack: `02-repository-semantic-intelligence`
- Kernel: `K2 Repository Semantic Compiler`
- Priority: `P1`
- Capability: 关联需求、Issue、讨论、代码变更、回滚和设计理由。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
