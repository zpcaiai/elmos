---
name: public-service-identity-case-and-record-model
description: "Execute authoritative Batch 17 Skill 642 for public service identity case and record model. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Public Service Identity Case And Record Model

## Operating contract

Apply authoritative Batch 17 Skill 642. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Identity

* 个人；
  -企业；
  -代理人；
  -政府员工；
  -机构；
  -跨机构身份；
  -数字身份；
  -匿名公共访问。

## Case

```text
Application
Evidence
Review
Decision
Notification
Appeal
Closure
Retention
```

## Hard Rules

* 政府身份和平台账户分开；
* 代理授权有期限；
* Case决定保留依据；
* Records不可任意删除；
* Appeal独立；
* 公共数据和受限数据分开；
* 无障碍和多语言属于功能要求。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
