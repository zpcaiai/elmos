---
name: technology-standard-and-exception-governor
description: "Execute authoritative Batch 18 Skill 684 for 建立集团批准技术栈、生命周期和例外机制。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Technology Standard And Exception Governor

## Operating contract

Apply authoritative Batch 18 Skill 684. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

建立集团批准技术栈、生命周期和例外机制。

## Standards

```text
Programming Languages
Frameworks
Databases
Cloud
Containers
Messaging
Identity
Observability
CI/CD
Security
AI Models
```

## Exception Record

```yaml
technology_exception:
  technology: string
  reason: regulatory-or-business
  owner: string
  expiry: string
  exit_plan: string
```

## Hard Rules

* 目标不是只有一种技术；
* 标准需说明适用范围；
* 例外必须有期限或长期依据；
* 新项目优先使用标准；
* 并购遗留技术进入过渡状态；
* 标准变化需迁移计划；
* 架构委员会不能阻塞所有交付。

## Acceptance Criteria

* 技术组合复杂度可控；
* 例外可查询；
* EOL技术有退出路线；
* 新项目标准采用率提高；
* 集团采购和人才计划得到支持。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
