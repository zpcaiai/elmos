---
name: revenue-bookings-and-pipeline-planner
description: "Execute authoritative Batch 15 Skill 494 for 将订阅、专业服务、Marketplace、伙伴和用量收入纳入收入预测。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Revenue Bookings And Pipeline Planner

## Operating contract

Apply authoritative Batch 15 Skill 494. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将订阅、专业服务、Marketplace、伙伴和用量收入纳入收入预测。

## Revenue Types

```text
Subscription
Usage
Professional Services
Support
Private Deployment
Offline License
Marketplace
Partner
Training
```

## Revenue Bridge

```text
Opening ARR
+ New ARR
+ Expansion
- Contraction
- Churn
= Ending ARR
```

## Bookings与Revenue

分别管理：

* 签约；
  -订单；
  -Billings；
  -收入确认；
  -现金回款；
  -递延收入。

## Hard Rules

* Pipeline不能直接计入收入；
* Forecast需按概率和阶段；
* Professional Service收入与交付容量关联；
* Marketplace收入按净额或总额规则明确；
* 合同中的免费期需进入模型；
* Churn和Expansion需分开；
* Currency影响需说明。

## Acceptance Criteria

* 收入预测可分解；
* Bookings和Revenue不混淆；
* Pipeline与销售Forecast一致；
* 交付容量支持服务收入；
* ARR Bridge可重建；
* 实际偏差可解释。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
