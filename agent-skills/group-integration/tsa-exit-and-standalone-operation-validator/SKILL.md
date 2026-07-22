---
name: tsa-exit-and-standalone-operation-validator
description: "Execute authoritative Batch 18 Skill 728 for 验证业务在不依赖卖方服务的情况下独立运行。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Tsa Exit And Standalone Operation Validator

## Operating contract

Apply authoritative Batch 18 Skill 728. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

验证业务在不依赖卖方服务的情况下独立运行。

## Exit Gate

```text
Replacement Service Ready
Data Complete
Identity Independent
Support Ready
Backup and DR Ready
Security Ready
Billing Ready
Users Migrated
```

## Hard Rules

* TSA退出需实际演练；
* 不能仅依靠项目报告；
* 最后一日Delta核对；
* Support和Incident独立；
* 旧访问立即撤销；
* 延期需商业审批；
* 退出后监控稳定期。

---

# 十二、协同收益Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
