---
name: group-business-capability-map
description: "Execute authoritative Batch 18 Skill 679 for 建立跨法人、品牌和地区的集团业务能力地图。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Business Capability Map

## Operating contract

Apply authoritative Batch 18 Skill 679. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

建立跨法人、品牌和地区的集团业务能力地图。

## Capability层级

```text
Value Stream
→ Business Capability
→ Sub-capability
→ Process
→ Application
→ Data
```

## Hard Rules

* 能力不应以组织部门命名；
* 相同能力跨法人统一定义；
* 地区差异作为Variant；
* 能力Owner明确；
* 应用必须映射业务能力；
* 战略关键能力标记；
* 处置决策使用能力地图。

## Acceptance Criteria

* 业务和IT使用统一语言；
* 能力重复可识别；
* 目标Operating Model可设计；
* 应用组合可按能力查看；
* 投资和退役优先级更清晰。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
