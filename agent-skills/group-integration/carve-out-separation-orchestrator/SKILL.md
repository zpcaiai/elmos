---
name: carve-out-separation-orchestrator
description: "Execute authoritative Batch 18 Skill 725 for 把出售或拆分业务从集团系统中安全分离。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Carve Out Separation Orchestrator

## Operating contract

Apply authoritative Batch 18 Skill 725. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

把出售或拆分业务从集团系统中安全分离。

## Separation Domains

```text
Identity
Network
Applications
Data
Finance
HR
Customer
Supplier
Security
Operations
Contracts
```

## Hard Rules

* Separation Perimeter明确；
* 共享系统逐项识别；
* 数据复制符合最小必要；
* IP和源码归属确认；
* TSA有结束日期；
* 残留访问撤销；
* 分离后的独立能力经过验证。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
