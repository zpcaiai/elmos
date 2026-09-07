---
name: integration-observability-and-flow-monitor
description: "Execute authoritative Batch 18 Skill 711 for integration observability and flow monitor. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Integration Observability And Flow Monitor

## Operating contract

Apply authoritative Batch 18 Skill 711. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Metrics

```text
Flow Volume
Latency
Error
Retry
Lag
Schema Failure
Duplicate
Missing
Consumer Health
```

## Hard Rules

* 跨公司链路有统一Correlation；
* 接口黑洞为0；
* 失败告警有Owner；
* 业务和技术错误分开；
* 过渡接口单独标记；
* TSA接口可监控；
* 退役前确认流量为0。

---

# 九、基础设施与运营Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
