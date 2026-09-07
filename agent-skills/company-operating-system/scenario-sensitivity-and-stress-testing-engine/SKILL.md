---
name: scenario-sensitivity-and-stress-testing-engine
description: "Execute authoritative Batch 15 Skill 500 for 评估关键假设变化对收入、现金、Runway和战略的影响。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Scenario Sensitivity And Stress Testing Engine

## Operating contract

Apply authoritative Batch 15 Skill 500. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

评估关键假设变化对收入、现金、Runway和战略的影响。

## Sensitivity Variables

```text
Win Rate
Sales Cycle
ACV
Churn
Expansion
Hiring
Salary
Model Cost
Cloud Cost
Delivery Productivity
Fundraising Timing
Exchange Rate
```

## Stress Cases

```text
Revenue下降30%
融资延迟六个月
Top Customer流失
模型成本翻倍
安全事件导致销售暂停
招聘速度减半
交付周期延长
```

## Hard Rules

* 情景需包含行动方案；
* Severe Downside不能只展示数字；
* 相关变量不能假设完全独立；
* Stress Test需考虑现金；
* 不得只测试乐观情景；
* 董事会需看到重大生存风险；
* 结果需影响Contingency。

## Acceptance Criteria

* 关键变量敏感性明确；
* 生存风险可见；
* 管理行动提前定义；
* 融资需求可评估；
* 战略更具韧性；
* Downside计划可执行。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
