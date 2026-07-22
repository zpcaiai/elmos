---
name: telecom-reference-architecture
description: "Execute authoritative Batch 17 Skill 660 for telecom reference architecture. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Telecom Reference Architecture

## Operating contract

Apply authoritative Batch 17 Skill 660. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

```text
Digital Channels
→ Customer/Product/Order
→ Service Orchestration
→ BSS Charging/Billing
→ OSS Inventory/Assurance
→ Network Function/API Layer
→ Network and Edge
```

支持：

* SBA；
  -Event Streaming；
  -高吞吐Mediation；
  -Edge；
  -多区域；
  -Carrier-grade HA；
  -实时和离线计费。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
