---
name: strategic-diagnosis-and-scenario-planner
description: "Execute authoritative Batch 15 Skill 463 for 评估公司内外部现状，形成战略问题、假设和未来情景。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Strategic Diagnosis And Scenario Planner

## Operating contract

Apply authoritative Batch 15 Skill 463. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

评估公司内外部现状，形成战略问题、假设和未来情景。

## External Diagnosis

```text
市场规模
增长趋势
客户需求
竞争
技术变化
监管
资本环境
人才
渠道
宏观风险
```

## Internal Diagnosis

```text
产品
技术
客户
销售
交付
增长
组织
人才
现金
品牌
数据
生态
```

## Strategic Issue

```yaml
strategic_issue:
  issue_id: enterprise-sales-cycle
  statement: 企业销售周期过长限制增长
  evidence: []
  root_causes: []
  strategic_importance: high
```

## Scenarios

建议至少：

```text
Base Case
Upside Case
Downside Case
Severe Downside
Strategic Opportunity Case
```

## Hard Rules

* 诊断必须区分事实与假设；
* 不得只使用内部意见；
* 竞争情报需合法获取；
* 情景必须影响资源和现金计划；
* Severe Downside必须可生存；
* 不确定性不能被单点预测掩盖；
* 每个重大假设需有验证方法。

## Acceptance Criteria

* 关键战略问题明确；
* 外部和内部事实完整；
* 情景可进入财务模型；
* 假设有Owner；
* 战略决策基于诊断；
* 重大未知项可追踪。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
