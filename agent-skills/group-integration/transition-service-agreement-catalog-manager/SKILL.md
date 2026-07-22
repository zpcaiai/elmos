---
name: transition-service-agreement-catalog-manager
description: "Execute authoritative Batch 18 Skill 681 for 管理TSA服务、费用、SLA、依赖和退出路线。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Transition Service Agreement Catalog Manager

## Operating contract

Apply authoritative Batch 18 Skill 681. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

管理TSA服务、费用、SLA、依赖和退出路线。

## TSA Service

```yaml
tsa_service:
  service_id: legacy-payroll
  provider_entity: seller
  consumer_entity: buyer
  start_date: string
  end_date: string
  monthly_cost: number
  exit_dependencies: []
```

## TSA范围

* IT；
  -身份；
  -网络；
  -数据中心；
  -财务；
  -HR；
  -采购；
  -客户支持；
  -安全；
  -报表；
  -许可证。

## Hard Rules

* 每项TSA必须有Exit Owner；
* 结束日期和延长期限明确；
* TSA成本进入整合财务；
* SLA和责任边界明确；
* TSA变更需正式审批；
* 延长TSA需说明根因；
* 无退出计划的TSA不得批准。

## Acceptance Criteria

* TSA清单完整；
* 每项有退出路线；
* 成本和风险可见；
* SLA可监控；
* TSA按期退出率可衡量。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
