---
name: industry-deployment-isolation-profile-manager
description: "Execute authoritative Batch 17 Skill 607 for 为行业定义默认部署、隔离、边缘、离线和高可用要求。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Deployment Isolation Profile Manager

## Operating contract

Apply authoritative Batch 17 Skill 607. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

为行业定义默认部署、隔离、边缘、离线和高可用要求。

## Profiles

```text
Finance：Dedicated、Private Runner、HSM
Manufacturing：Edge、Plant、Offline
Energy：Critical Zone、Air-gapped
Healthcare：Private、Regional Residency
Government：Sovereign、Air-gapped
Ecommerce：Cloud-scale、Multi-region
Telecom：Distributed Edge、Carrier-grade
```

## Hard Rules

* Profile是建议起点，不是法规结论；
* 客户风险评估可收紧；
* OT和IT边界明确；
* Edge断连行为需定义；
* Offline升级有路径；
* Dedicated部署仍需Tenant控制；
* Profile变化影响报价和SLA。

## Acceptance Criteria

* 行业默认部署可用；
* 隔离满足风险；
* 网络和数据流明确；
* HA/DR目标可配置；
* 成本可估算；
* POC和Production Profile分开。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
