---
name: business-readiness-and-integration-acceptance
description: "Execute authoritative Batch 18 Skill 743 for business readiness and integration acceptance. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Business Readiness And Integration Acceptance

## Operating contract

Apply authoritative Batch 18 Skill 743. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Acceptance Dimensions

```text
Business
Technology
Data
Identity
Security
Operations
Finance
Legal
People
Customer
```

## Hard Rules

* 技术上线不等于业务准备；
* 用户、支持和流程均需就绪；
* 条件验收有Owner和期限；
* Critical条件不能通过；
* 业务Owner正式签字；
* 收益和风险同时确认；
* 验收绑定具体Wave和版本。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
