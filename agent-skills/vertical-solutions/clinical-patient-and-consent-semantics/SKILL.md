---
name: clinical-patient-and-consent-semantics
description: "Execute authoritative Batch 17 Skill 635 for clinical patient and consent semantics. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Clinical Patient And Consent Semantics

## Operating contract

Apply authoritative Batch 17 Skill 635. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Patient Identity

处理：

* MRN；
  -国家ID；
  -机构ID；
  -Master Patient Index；
  -合并；
  -拆分；
  -重复患者；
  -匿名；
  -代理人。

## Consent

```text
Purpose
Scope
Data Category
Recipient
Time
Revocation
Emergency Override
```

## Hard Rules

* 患者合并不可仅按姓名；
* Consent撤销影响后续访问；
* 临床数据不允许普通覆盖更新；
* Provenance保留；
* Break-glass需审计；
* 敏感医疗类别可有更严格控制；
* Agent不得自主作出临床最终决定。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
