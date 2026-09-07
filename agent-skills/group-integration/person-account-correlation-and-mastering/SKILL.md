---
name: person-account-correlation-and-mastering
description: "Execute authoritative Batch 18 Skill 692 for 关联两家公司中的同一员工、承包商、客户或合作伙伴身份。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Person Account Correlation And Mastering

## Operating contract

Apply authoritative Batch 18 Skill 692. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

关联两家公司中的同一员工、承包商、客户或合作伙伴身份。

## Match Signals

```text
Employee ID
Verified Email
Legal Identity
HR Record
Manager
Organization
Contract
External Identifier
```

## Hard Rules

* 不能仅按姓名匹配；
* 自动匹配需置信度；
* 冲突需人工处理；
* 同一人多个角色允许保留；
* 个人和服务身份不可合并；
* 匹配证据需保护隐私；
* Master ID变更有审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
