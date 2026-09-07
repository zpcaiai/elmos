---
name: onboarding-probation-and-time-to-productivity-manager
description: "Execute authoritative Batch 15 Skill 485 for 帮助新员工快速理解公司、角色、系统和成功标准。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Onboarding Probation And Time To Productivity Manager

## Operating contract

Apply authoritative Batch 15 Skill 485. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

帮助新员工快速理解公司、角色、系统和成功标准。

## Onboarding Stages

```text
Preboarding
Day 1
Week 1
Day 30
Day 60
Day 90
Probation Review
```

## Onboarding Plan

```yaml
onboarding_plan:
  employee_id: string
  role_id: string
  manager: string
  buddy: string
  first_90_day_outcomes: []
```

## 内容

* Mission；
  -Strategy；
  -Product；
  -Customer；
  -Security；
  -Role；
  -Tools；
  -Team；
  -Operating Cadence；
  -Decision Rights；
  -First Deliverable。

## Hard Rules

* Onboarding不只是HR手续；
* Manager对生产力负责；
* Access遵循最小权限；
* 第一个月不应缺少明确工作；
* Probation标准需提前说明；
* 远程员工需同等支持；
* Onboarding反馈需改进系统。

## Acceptance Criteria

* 新员工知道成功标准；
* Access按时完成；
* First Value时间缩短；
* Probation决策有证据；
* 新员工Retention提高；
* Manager履行Onboarding责任。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
