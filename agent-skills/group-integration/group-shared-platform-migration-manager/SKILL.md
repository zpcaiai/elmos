---
name: group-shared-platform-migration-manager
description: "Execute authoritative Batch 18 Skill 687 for 迁移身份、消息、数据、API、监控、财务等共享平台。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Shared Platform Migration Manager

## Operating contract

Apply authoritative Batch 18 Skill 687. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

迁移身份、消息、数据、API、监控、财务等共享平台。

## Shared Platforms

```text
Identity
API Gateway
Event Platform
Data Platform
Observability
Service Management
Finance Platform
HR Platform
Security Platform
```

## Hard Rules

* Shared Platform迁移需独立容量计划；
* 内部客户和SLO明确；
* 不允许多个共享平台无治理长期共存；
* 大规模迁移分批；
* 失败有Fallback；
* 数据和权限迁移同步；
* 成本分摊模型明确。

## Acceptance Criteria

* 目标共享平台可承载集团负载；
* 内部客户迁移计划完整；
* 双平台期受控；
* 服务质量稳定；
* 重复平台开始退出。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
