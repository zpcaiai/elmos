---
name: integration-wave-and-migration-factory-planner
description: "Execute authoritative Batch 18 Skill 688 for 按业务、依赖、地区和风险建立迁移Wave。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Integration Wave And Migration Factory Planner

## Operating contract

Apply authoritative Batch 18 Skill 688. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

按业务、依赖、地区和风险建立迁移Wave。

## Wave分组

```text
Business Capability
Legal Entity
Region
Application Cluster
Data Domain
Technology Stack
TSA Dependency
```

## Wave Gate

```text
Discover
Assess
Design
Build
Validate
Cutover
Hypercare
Retire
```

## Hard Rules

* Wave不能只按应用数量平均；
* 同一强依赖Cluster尽量同Wave；
* 首Wave选择代表性但风险可控资产；
* 关键财务期和生产冻结期纳入；
* 产能和客户参与度匹配；
* 每Wave有收益目标；
* Wave间积累Recipe和学习。

## Acceptance Criteria

* Wave顺序合理；
* 关键依赖被考虑；
* 迁移工厂可复用前Wave资产；
* 计划和收益同步；
* 每Wave可独立验收。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
