---
name: valuation-dilution-and-fundraising-modeler
description: "Execute authoritative Batch 15 Skill 508 for 分析不同融资金额、估值、期权池和条款对稀释及公司资本的影响。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Valuation Dilution And Fundraising Modeler

## Operating contract

Apply authoritative Batch 15 Skill 508. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

分析不同融资金额、估值、期权池和条款对稀释及公司资本的影响。

## Model Inputs

```text
Pre-money
New Money
Option Pool
Existing Cap Table
Notes
SAFEs
Warrants
Liquidation Preference
Participation
Anti-dilution
```

## Scenario

```yaml
funding_scenario:
  pre_money: number
  raise: number
  post_money: number
  new_investor_ownership: number
  founder_dilution: number
```

## Hard Rules

* Fully Diluted口径需统一；
* 期权池Pre或Post需明确；
* SAFE和可转债需正确处理；
* 估值与条款一起分析；
* 不能只比较表面估值；
* 税务和法律结果需专业确认；
* 董事会和股东审批按要求执行。

## Acceptance Criteria

* 稀释清晰；
* 多情景可比较；
* Cap Table可更新；
* 条款经济影响可见；
* 创始人和董事会理解结果；
* Closing后数字准确。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
