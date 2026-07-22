---
name: integration-incident-command-and-freeze-manager
description: "Execute authoritative Batch 18 Skill 742 for 处理Day 1、身份、数据、Cutover和TSA退出事故。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Integration Incident Command And Freeze Manager

## Operating contract

Apply authoritative Batch 18 Skill 742. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

处理Day 1、身份、数据、Cutover和TSA退出事故。

## Freeze Levels

```text
Stop New Changes
Stop Wave Expansion
Freeze Data Writes
Freeze Identity Changes
Rollback Current Wave
Full Integration Pause
```

## Hard Rules

* SEV事件单一指挥；
* 数据完整性优先；
* Freeze不依赖故障系统；
* 证据保全；
* 业务和监管沟通明确；
* 恢复前重新验证；
* 事故形成新Gate。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
