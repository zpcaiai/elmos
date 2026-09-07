---
name: role-permission-and-separation-of-duties-harmonizer
description: "Execute authoritative Batch 18 Skill 695 for 协调双方Role、Group、Permission和职责分离规则。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Role Permission And Separation Of Duties Harmonizer

## Operating contract

Apply authoritative Batch 18 Skill 695. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

协调双方Role、Group、Permission和职责分离规则。

## Hard Rules

* 同名Role不代表同权限；
* 合并默认取最小必要权限；
* 高权限需重新认证；
* SoD冲突自动发现；
* 历史访问不自动保留；
* 地区和法人限制继续生效；
* 权限变化通知Owner。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
