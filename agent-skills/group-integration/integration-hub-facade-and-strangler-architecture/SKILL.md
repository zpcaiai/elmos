---
name: integration-hub-facade-and-strangler-architecture
description: "Execute authoritative Batch 18 Skill 708 for 通过Facade、API Gateway、Event Hub和Strangler降低直接耦合。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Integration Hub Facade And Strangler Architecture

## Operating contract

Apply authoritative Batch 18 Skill 708. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

通过Facade、API Gateway、Event Hub和Strangler降低直接耦合。

## Hard Rules

* Integration Hub不能变成所有逻辑的God Layer；
* 新接口优先Canonical Contract；
* 旧系统通过Adapter隔离；
* Facade有退出或长期定位；
* 延迟和可用性预算明确；
* 安全和审计统一；
* 接口版本有生命周期。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
