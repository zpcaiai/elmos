---
name: procurement-vendor-and-contract-integration
description: "Execute authoritative Batch 18 Skill 721 for 整合供应商、采购、合同、License和付款条件。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Procurement Vendor And Contract Integration

## Operating contract

Apply authoritative Batch 18 Skill 721. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

整合供应商、采购、合同、License和付款条件。

## Hard Rules

* 同一供应商实体解析；
* 重复合同识别；
* 价格和期限比较；
* 终止和转让条款需法务确认；
* Vendor风险重新评估；
* 集中采购收益可测；
* 不影响关键供应连续性。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
