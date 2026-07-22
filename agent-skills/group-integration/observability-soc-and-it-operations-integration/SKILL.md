---
name: observability-soc-and-it-operations-integration
description: "Execute authoritative Batch 18 Skill 717 for observability soc and it operations integration. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Observability Soc And It Operations Integration

## Operating contract

Apply authoritative Batch 18 Skill 717. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## 范围

```text
Metrics
Logs
Traces
SIEM
SOC
NOC
Alert
On-call
Runbook
Incident
Problem
Change
```

## Hard Rules

* 告警在切换前接入；
* 双系统期间去重事件；
* On-call责任明确；
* 日志驻留符合要求；
* 监控缺失阻止Cutover；
* 重大事件使用统一指挥；
* 旧工具退役需数据导出。

---

# 十、业务平台整合Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
