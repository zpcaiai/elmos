# 与既有 Elmos v3 / Router / 认证体系兼容

本包是 assurance extension，不更换八核或现有route owner。既有资料中K8承担独立证书签署，已有scope compiler、holdout与assurance-case方向，本包优先复用并补齐实际缺口。

## Bootstrap必须建立实际映射

`existing module/path → this package contract → reuse | extend | absent | conflict`。
确认业务线dispatcher/16 canonical routes，不允许仅根据旧文档推断当前代码一致。若不一致，记录真实数量与迁移需求，不强改回假定值。

## E0–E5

旧文档对E级含义可能不同。本包使用namespace `elmos.assurance/v4`；历史证书保持旧profile ID、原字段、原有效期。显式迁移mapping要说明是否需要重跑，不给老E5自动换新E5徽章。
JSON Schema兼容以N-1 fixtures验证；breaking字段使用versioned envelope和upcaster。未知版本fail closed，不默默忽略字段。

## Router/Harness

每模型调用接收已持久 `ModelExecutionPlan`，经Elmos-owned policy routing。Direct/LiteLLM/OpenRouter不进入领域DTO。审计/测试生成不例外，但使用隔离purpose/security context与cost center。
模型输出只是CandidateArtifact/TestCandidate/ProofCandidate/FindingCandidate；需验证器接收并commit才能成为事实。

## 渐进发布

feature flags: assurance_v4_shadow、contract_ir_v4、ethen_external_audit、formal_strict、k8_v4_signing。
先shadow读既有任务→比较旧新决策→人工核对差异→小scope执行→Ethen审核→才允许新签署。
回滚关闭新admission；在途run按原profile安全完成或取消；不得删除新证据/回滚撤销记录。

## 不新增平行事实源

引用现有Tenant/Project/Task/Artifact/Usage模型，保留其主键/租户控制。示例迁移带独立schema只为评审，正式落地按实际实体归并。Skill文档中模块路径为逻辑建议，不是现有repo事实。
