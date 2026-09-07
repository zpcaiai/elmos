---
name: energy-critical-infrastructure-control-pack
description: "Execute authoritative Batch 17 Skill 629 for energy critical infrastructure control pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Energy Critical Infrastructure Control Pack

## Operating contract

Apply authoritative Batch 17 Skill 629. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Control Areas

```text
Asset Categorization
Electronic Perimeter
Remote Access
Change Management
Configuration
Incident
Recovery
Supply Chain
Physical Access
Logging
Personnel
```

## Hard Rules

* 不同地区使用各自监管Overlay；
* Cyber Asset分类需客户确认；
* 关键区域默认无公网；
* Remote Access强审计；
* Patch需兼顾可靠性；
* 时间同步受保护；
* Critical Control失败阻止交付。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
