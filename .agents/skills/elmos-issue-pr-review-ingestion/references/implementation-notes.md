# Implementation Notes

- Skill ID: `issue-pr-review-ingestion`
- Pack: `01-knowledge-ingestion-governance`
- Kernel: `K1 Knowledge Fabric`
- Priority: `P1`
- Capability: 沉淀 Issue、PR、代码审查意见、提交理由与最终修复之间的因果和语义关系。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
