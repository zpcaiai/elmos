---
name: industry-slo-telemetry-and-dashboard-manager
description: "Execute authoritative Batch 17 Skill 608 for 定义行业关键SLI、SLO、业务指标和监管证据Dashboard。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Slo Telemetry And Dashboard Manager

## Operating contract

Apply authoritative Batch 17 Skill 608. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

定义行业关键SLI、SLO、业务指标和监管证据Dashboard。

## Examples

```text
金融：交易正确性、对账差异、结算延迟
制造：周期时间、停机、报警、设备可用性
能源：遥测新鲜度、调度成功、停电恢复
医疗：患者匹配、医嘱延迟、临床系统可用性
电商：下单率、库存准确、支付成功、履约时效
通信：会话建立、使用量处理、计费准确、网络功能可用性
```

## Hard Rules

* 行业SLO需业务Owner批准；
* 正确性和Safety不能被Availability代替；
* Metric标签不得泄露敏感信息；
* Dashboard需区分业务和技术；
* 监管报告和运维指标使用同一事实；
* Missing Telemetry阻止关键Gate；
* SLO按地区和Segment可覆盖。

## Acceptance Criteria

* 关键业务旅程有SLI；
* Control Evidence可查询；
* SLO可自动计算；
* Alert和Runbook完整；
* 行业管理层可理解；
* 迁移前后可比较。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
