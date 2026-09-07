---
name: operating-review-and-variance-correction-manager
description: "Execute authoritative Batch 15 Skill 475 for 将指标偏差转化为根因分析、纠正行动和战略更新。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Operating Review And Variance Correction Manager

## Operating contract

Apply authoritative Batch 15 Skill 475. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

将指标偏差转化为根因分析、纠正行动和战略更新。

## Review Chain

```text
Target
→ Actual
→ Variance
→ Root Cause
→ Forecast Impact
→ Corrective Action
→ Owner
→ Verification
```

## Variance Types

```text
Timing
Volume
Price
Conversion
Productivity
Quality
Cost
Capacity
External
Assumption Failure
```

## Hard Rules

* 不能只解释结果而无行动；
* 区分可控与不可控；
* 一次性和结构性原因分开；
* 偏差需影响Forecast；
* 纠正行动不得破坏Guardrail；
* 连续偏差需升级战略问题；
* 管理层不能通过重新定义指标消除偏差。

## Acceptance Criteria

* 重大偏差有根因；
* Forecast得到更新；
* 纠正行动可追踪；
* 行动效果被验证；
* 结构性问题进入战略；
* 重复偏差减少。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
