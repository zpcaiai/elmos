---
name: customer-channel-and-digital-experience-integration
description: "Execute authoritative Batch 18 Skill 724 for customer channel and digital experience integration. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Customer Channel And Digital Experience Integration

## Operating contract

Apply authoritative Batch 18 Skill 724. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## 范围

```text
Website
Mobile
Portal
Contact Center
Identity
Loyalty
Notification
Brand
Payment
```

## Hard Rules

* 品牌策略先明确；
* 客户账号合并需谨慎；
* Loyalty余额不可丢失；
* 登录迁移可回滚；
* 通知Consent保留；
* 客户渠道切换有Fallback；
* 用户体验指标持续监控。

---

# 十一、Carve-out与TSA退出Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
