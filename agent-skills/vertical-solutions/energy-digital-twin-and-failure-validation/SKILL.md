---
name: energy-digital-twin-and-failure-validation
description: "Execute authoritative Batch 17 Skill 631 for energy digital twin and failure validation. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Energy Digital Twin And Failure Validation

## Operating contract

Apply authoritative Batch 17 Skill 631. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Cases

```text
通信中断
设备故障
遥测延迟
错误测量
网络分区
预测偏差
负荷突变
储能不可用
调度失败
黑启动和恢复模拟
```

## Gate

* 不产生危险控制；
  -关键Telemetry可恢复；
  -调度结果符合约束；
  -异常可告警；
  -恢复过程可复现。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
