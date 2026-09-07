---
name: grid-metering-and-dispatch-semantics
description: "Execute authoritative Batch 17 Skill 628 for grid metering and dispatch semantics. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Grid Metering And Dispatch Semantics

## Operating contract

Apply authoritative Batch 17 Skill 628. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## 关键语义

* Telemetry；
  -Command；
  -Setpoint；
  -Measurement Quality；
  -State Estimation；
  -Forecast；
  -Dispatch；
  -Outage；
  -Restoration；
  -Meter Interval；
  -Time Synchronization。

## Hard Rules

* 测量值与质量标志一起迁移；
* Command和Confirmation分开；
* Event Time与Processing Time分开；
* 计量修正保留版本；
* 拓扑变化影响计算；
* 控制指令需严格Authorization；
* 关键动作保留人工或操作员边界。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
