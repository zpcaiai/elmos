---
name: group-integration-governance-and-decision-rights
description: "Execute authoritative Batch 18 Skill 735 for group integration governance and decision rights. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Integration Governance And Decision Rights

## Operating contract

Apply authoritative Batch 18 Skill 735. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Governance Layers

```text
Board
Executive Steering Committee
IMO
Architecture Council
Data Council
Security Council
Workstream
```

## Reserved Decisions

* Target Operating Model；
  -核心平台选择；
  -重大数据合并；
  -TSA延长；
  -重大一次性成本；
  -法人和地区例外；
  -大规模人员调整；
  -重大风险接受。

## Hard Rules

* 决策权限明确；
* 自我审批受限；
* 紧急决策事后复核；
* 两家公司管理者参与；
* 决策记录完整；
* 冲突升级有路径；
* 治理随整合阶段简化。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
