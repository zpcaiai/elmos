---
name: operating-financial-variance-diagnostic
description: "Execute authoritative Batch 15 Skill 502 for 把经营指标与财务偏差联合分析。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Operating Financial Variance Diagnostic

## Operating contract

Apply authoritative Batch 15 Skill 502. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

把经营指标与财务偏差联合分析。

## Variance Bridge

```text
Revenue：
Volume
Price
Mix
Timing
Churn
FX

Cost：
Headcount
Salary
Cloud
Model
Usage
Vendor
Timing
One-time
```

## Root Cause

例如：

```text
收入低于预算
→ POC数量正常
→ POC转化下降
→ 安全审查周期延长
→ Private Runner证据不足
```

## Hard Rules

* 财务偏差需关联经营事实；
* 不只用“时点差异”解释所有问题；
* 结构性偏差需进入战略；
* 部门Owner参与根因；
* 一次性调整需单独显示；
* 纠正措施进入Forecast；
* 数据质量不足需明确。

## Acceptance Criteria

* 财务数字可解释；
* 经营团队理解影响；
* 纠正行动可量化；
* Forecast更准确；
* 重复偏差减少；
* 资源分配可以调整。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
