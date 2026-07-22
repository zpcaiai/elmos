---
name: security-control-baseline-harmonizer
description: "Execute authoritative Batch 18 Skill 713 for security control baseline harmonizer. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Security Control Baseline Harmonizer

## Operating contract

Apply authoritative Batch 18 Skill 713. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## 范围

```text
Identity
Endpoint
Network
Cloud
Application
Data
Vulnerability
Logging
Incident
Third Party
```

## Hard Rules

* 不默认选择较弱控制；
* Control差异有风险决策；
* Day 1最低安全基线明确；
* 合并SOC视图；
* 严重漏洞优先修复；
* 安全例外有期限；
* 集团控制映射法人要求。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
