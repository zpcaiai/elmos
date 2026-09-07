---
name: group-canonical-data-model
description: "Execute authoritative Batch 18 Skill 699 for 建立集团Canonical Model，同时保留地区和业务Variant。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Canonical Data Model

## Operating contract

Apply authoritative Batch 18 Skill 699. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

建立集团Canonical Model，同时保留地区和业务Variant。

## Hard Rules

* Canonical不意味着物理Schema统一；
* 业务含义优先；
* Source字段血缘保留；
* Variant显式；
* Code Set统一治理；
* 模型版本化；
* 不可映射字段不得静默丢弃。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
