---
name: synergy-model-builder
description: "Execute authoritative Batch 18 Skill 729 for synergy model builder. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Synergy Model Builder

## Operating contract

Apply authoritative Batch 18 Skill 729. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Synergy Categories

```text
Application Retirement
License Consolidation
Cloud and Data Center
Vendor Consolidation
Workforce Productivity
Shared Services
Revenue Cross-sell
Data and Analytics
Faster Product Delivery
Risk Reduction
```

## Synergy Record

```yaml
synergy:
  synergy_id: duplicate-crm-retirement
  category: cost
  baseline: number
  run_rate_target: number
  one_time_cost: number
  owner: string
  enabling_initiatives: []
```

## Hard Rules

* 每项收益有Baseline；
* 防止重复计算；
* 收益和技术行动关联；
* 时间到Run-rate明确；
* 风险和依赖可见；
* 未实现收益不提前确认；
* Revenue Synergy与Cost Synergy分开。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
