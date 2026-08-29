# Implementation Notes

- Skill ID: `disagreement-adjudication`
- Pack: `14-human-governance-operations`
- Kernel: `Human Assurance Plane`
- Priority: `P0`
- Capability: 对模型、规则和专家分歧执行二审、仲裁和决策依据沉淀。

实现应优先复用 Semantic IR、Evidence Store、Policy Engine、Trace 和 Registry 接口；不得在 Skill 内创建绕过平台治理的第二套状态或权限系统。
