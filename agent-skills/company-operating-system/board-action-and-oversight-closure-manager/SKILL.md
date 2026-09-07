---
name: board-action-and-oversight-closure-manager
description: "Execute authoritative Batch 15 Skill 521 for 追踪董事会决策、条件、请求和管理层行动。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Board Action And Oversight Closure Manager

## Operating contract

Apply authoritative Batch 15 Skill 521. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

追踪董事会决策、条件、请求和管理层行动。

## Board Action

```yaml
board_action:
  action_id: string
  source_meeting: string
  owner: string
  due_date: string
  status: open
  evidence: []
```

## Action Types

```text
Management Action
Additional Analysis
Risk Mitigation
Hiring
Financing
Policy
Customer
Security
Strategic Review
```

## Hard Rules

* 董事会行动不能只留在Minutes；
* 每项有Owner和日期；
* 逾期需在下一次会议报告；
* 完成需证据；
* 条件批准事项需确认条件满足；
* 董事请求和管理建议需区分；
* 重复未完成项需升级。

## Acceptance Criteria

* Board Action可见；
* 逾期及时升级；
* 证据完整；
* 决议条件得到满足；
* 管理层问责清晰；
* 董事会监督形成闭环。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
