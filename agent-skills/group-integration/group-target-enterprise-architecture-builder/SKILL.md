---
name: group-target-enterprise-architecture-builder
description: "Execute authoritative Batch 18 Skill 683 for 定义集团目标业务、数据、应用、集成、技术和安全架构。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Target Enterprise Architecture Builder

## Operating contract

Apply authoritative Batch 18 Skill 683. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

定义集团目标业务、数据、应用、集成、技术和安全架构。

## Architecture Domains

```text
Business
Application
Data
Integration
Identity
Security
Technology
Cloud
Operations
AI
```

## Target State Horizon

```text
Day 1
Transitional
Day 100
Year 1
Long-term
```

## Hard Rules

* 目标架构需支持过渡状态；
* 不以单一厂商产品代替架构；
* 目标状态必须考虑地区差异；
* Shared Platform有内部SLO；
* 数据和身份优先级明确；
* 迁移路径与架构同时设计；
* 架构与Synergy一致。

## Acceptance Criteria

* 目标状态清晰；
* Transitional Architecture可运行；
* 应用处置可映射目标架构；
* 技术标准和例外可管理；
* 管理层批准架构原则。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
