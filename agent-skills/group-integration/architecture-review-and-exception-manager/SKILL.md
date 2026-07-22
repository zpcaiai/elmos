---
name: architecture-review-and-exception-manager
description: "Execute authoritative Batch 18 Skill 736 for 统一审查目标架构、应用处置、数据和技术例外。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Architecture Review And Exception Manager

## Operating contract

Apply authoritative Batch 18 Skill 736. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

统一审查目标架构、应用处置、数据和技术例外。

## Hard Rules

* Review聚焦重大决策；
* 标准项目使用快速通道；
* 例外有Owner和期限；
* 不以架构治理拖延Day 1；
* 跨行业和地区要求可覆盖；
* 决策可回溯；
* 例外数量持续下降。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
