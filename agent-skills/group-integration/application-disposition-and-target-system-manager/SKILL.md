---
name: application-disposition-and-target-system-manager
description: "Execute authoritative Batch 18 Skill 678 for 为每项应用确定目标处置方式。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Application Disposition And Target System Manager

## Operating contract

Apply authoritative Batch 18 Skill 678. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

为每项应用确定目标处置方式。

## Disposition

```text
Retain
Invest
Migrate
Translate
Replatform
Refactor
Replace
Consolidate
Wrap
Federate
Carve-out
Retire
```

## 决策维度

* 战略适配；
  -业务能力；
  -技术健康；
  -风险；
  -成本；
  -用户；
  -数据；
  -法规；
  -迁移复杂度；
  -协同收益。

## Hard Rules

* 每项应用只能有一个当前Disposition；
* 未确认目标能力不能Retire；
* 高风险替换需双运行；
* Replace需包含数据和接口迁移；
* Retain也需明确治理状态；
* 决策变更保留历史；
* 无业务Owner确认不得关闭关键应用。

## Acceptance Criteria

* 组合处置覆盖完整；
* 目标系统明确；
* 处置与交易逻辑一致；
* 时间和成本可估算；
* 退役前提可查询。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
