---
name: industry-reference-architecture-builder
description: "Execute authoritative Batch 17 Skill 606 for 定义可组合、可替换的行业目标架构，而不是固定单一厂商方案。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Reference Architecture Builder

## Operating contract

Apply authoritative Batch 17 Skill 606. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

定义可组合、可替换的行业目标架构，而不是固定单一厂商方案。

## Architecture Layers

```text
Experience
Domain Services
Workflow
Data
Integration
Security
Observability
Operations
AI/Agent
Edge/Device
```

## Variant Profiles

```text
Cloud-native
Hybrid
Private Cloud
On-premise
Air-gapped
Edge
Mission-critical HA
```

## Hard Rules

* Reference Architecture不能绑定单一云厂商；
* 必须标明可替换组件；
* Control映射到架构；
* 数据流和信任边界明确；
* 与Batch 12部署模式兼容；
* 旧系统共存和Cutover纳入；
* 架构性能假设需验证。

## Acceptance Criteria

* 客户可选择适合Profile；
* 架构满足行业控制；
* 组件边界清晰；
* 迁移路径完整；
* Partner可按模板交付；
* Architecture Decision可追踪。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
