---
name: industry-domain-meta-model-builder
description: "Execute authoritative Batch 17 Skill 595 for 定义跨行业通用的领域元模型，使行业实体能够映射到UIR、API、数据、事件和控制。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Domain Meta Model Builder

## Operating contract

Apply authoritative Batch 17 Skill 595. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

定义跨行业通用的领域元模型，使行业实体能够映射到UIR、API、数据、事件和控制。

## Domain Meta-model

```text
Domain
├── Bounded Context
├── Aggregate
├── Entity
├── Value Object
├── Actor
├── Role
├── Command
├── Event
├── Policy
├── State Machine
├── Invariant
├── Calculation
├── External System
└── Evidence
```

## Domain Entity

```yaml
domain_entity:
  entity_id: healthcare.patient
  aggregate: patient
  identifiers: []
  attributes: []
  relationships: []
  lifecycle: []
  classifications: []
  control_refs: []
```

## Hard Rules

* 领域模型不能直接等于数据库表；
* 技术字段和业务含义分开；
* Aggregate边界必须有依据；
* 业务Invariant显式建模；
* 同名术语冲突需区分Context；
* 模型可映射源目标实现；
* 领域模型需领域Owner审批。

## Acceptance Criteria

* 行业实体和状态可查询；
* 领域关系可生成图谱；
* 数据、API和事件可关联；
* 控制可绑定实体和动作；
* 迁移差异可用行业语言表达；
* 模型支持客户扩展。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
