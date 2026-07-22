---
name: synergy-reconciliation-and-financial-acceptance
description: "Execute authoritative Batch 18 Skill 734 for 将计划、实际和财务账中的Synergy进行核对。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Synergy Reconciliation And Financial Acceptance

## Operating contract

Apply authoritative Batch 18 Skill 734. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

将计划、实际和财务账中的Synergy进行核对。

## Bridge

```text
Target Synergy
- Delay
- Scope Change
- Stranded Cost
- Leakage
+ Additional Synergy
= Actual Run-rate
```

## Hard Rules

* 财务和IMO使用同一口径；
* 一次性收益不算永久Run-rate；
* 收入协同使用实现收入；
* 收益调整有审批；
* 未实现项保留；
* 交易模型和实际比较；
* 董事会获得真实结果。

---

# 十三、集团治理与变革Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
