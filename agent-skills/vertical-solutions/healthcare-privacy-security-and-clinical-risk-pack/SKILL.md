---
name: healthcare-privacy-security-and-clinical-risk-pack
description: "Execute authoritative Batch 17 Skill 636 for healthcare privacy security and clinical risk pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Healthcare Privacy Security And Clinical Risk Pack

## Operating contract

Apply authoritative Batch 17 Skill 636. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Control Areas

```text
PHI Classification
Minimum Necessary
Consent
Break-glass
Audit
Identity
Device
Clinical Safety
Data Integrity
Availability
Business Associate/Processor
```

## Hard Rules

* 隐私规则按地区Overlay；
* Clinical Safety与Security共同评估；
* 测试数据必须脱敏或合成；
* Audit访问不可删除；
* 临床Decision Support需Human Oversight；
* Patient Access和更正流程纳入；
* 高风险临床功能需Safety Case。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
