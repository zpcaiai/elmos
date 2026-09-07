---
name: cap-table-and-equity-administration-manager
description: "Execute authoritative Batch 15 Skill 510 for 管理股东、股份、Option、SAFE、可转债和股权事件。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Cap Table And Equity Administration Manager

## Operating contract

Apply authoritative Batch 15 Skill 510. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

管理股东、股份、Option、SAFE、可转债和股权事件。

## Cap Table Entities

```text
Shareholder
Share Class
Share Issuance
Option Grant
Exercise
Vesting
SAFE
Convertible Note
Transfer
Repurchase
Cancellation
```

## Hard Rules

* Cap Table必须与法定记录一致；
* 每个股权事件有批准和文件；
* Vesting准确；
* 离职处理按协议；
* 期权池余额可查询；
* 股权数据严格保密；
* 模拟与正式Cap Table分开。

## Acceptance Criteria

* Fully Diluted所有权准确；
* 每个Grant有文件；
* 融资后Cap Table正确；
* Option余额清晰；
* 审计和税务资料可用；
* 董事会批准完整。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
