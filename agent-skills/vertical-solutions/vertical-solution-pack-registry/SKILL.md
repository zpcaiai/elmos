---
name: vertical-solution-pack-registry
description: "Execute authoritative Batch 17 Skill 594 for 登记VSP、地区Overlay、客户Extension和依赖关系。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Vertical Solution Pack Registry

## Operating contract

Apply authoritative Batch 17 Skill 594. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

登记VSP、地区Overlay、客户Extension和依赖关系。

## Asset Types

```text
Industry Base Pack
Industry Segment Pack
Regulatory Overlay
Jurisdiction Overlay
Customer Extension
Industry Recipe
Industry Evaluation Corpus
Industry Architecture
Industry Playbook
```

## Pack状态

```text
draft
research
design-partner
evaluating
certified
commercial
restricted
deprecated
retired
```

## Dependency Example

```yaml
pack_dependency:
  pack: healthcare-hospital-tw
  requires:
    - healthcare-core
    - fhir-interoperability
    - tw-health-regulatory-overlay
```

## Hard Rules

* Pack ID不可重用；
* 同一客户Extension不得被其他客户访问；
* 依赖版本必须锁定；
* 冲突Pack不能同时安装；
* 已废弃Pack需迁移计划；
* Commercial状态需通过行业Gate；
* Asset安装进入Provenance。

## Acceptance Criteria

* 所有行业资产可查询；
* 版本和兼容性清晰；
* 私有资产隔离；
* 地区Overlay组合正确；
* 更新和回滚可执行；
* Marketplace可引用同一注册表。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
