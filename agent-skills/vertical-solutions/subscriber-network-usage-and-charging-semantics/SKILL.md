---
name: subscriber-network-usage-and-charging-semantics
description: "Execute authoritative Batch 17 Skill 656 for subscriber network usage and charging semantics. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Subscriber Network Usage And Charging Semantics

## Operating contract

Apply authoritative Batch 17 Skill 656. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## 关键语义

* Subscriber Identity；
  -Service Entitlement；
  -Session；
  -Policy；
  -Usage；
  -Mediation；
  -Rating；
  -Charging；
  -Billing；
  -Provisioning；
  -Fault；
  -Inventory。

## Hard Rules

* Usage Event具有稳定ID；
* Event Time和Ingest Time分开；
* Late Event有处理策略；
* Charging Rule版本保留；
* Session关联完整；
* Subscriber Privacy受保护；
* Network Function和业务Service边界分开。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
