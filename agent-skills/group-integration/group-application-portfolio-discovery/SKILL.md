---
name: group-application-portfolio-discovery
description: "Execute authoritative Batch 18 Skill 674 for 盘点集团全部应用、产品、平台和业务能力。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Group Application Portfolio Discovery

## Operating contract

Apply authoritative Batch 18 Skill 674. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

盘点集团全部应用、产品、平台和业务能力。

## 应用记录

```yaml
application:
  application_id: string
  legal_entity: string
  business_capabilities: []
  owners: []
  users: []
  criticality: string
  regions: []
  lifecycle: string
  annual_cost: number
```

## 数据来源

* CMDB；
  -Git；
  -云账号；
  -DNS；
  -网络流量；
  -身份系统；
  -财务采购；
  -License；
  -APM；
  -数据库；
  -访谈；
  -影子IT扫描。

## Hard Rules

* CMDB不能作为唯一事实；
* SaaS、脚本和Excel也需盘点；
* 应用和仓库可能是多对多；
* 无Owner资产进入风险清单；
* 应用成本包括人员和基础设施；
* 实际流量用于验证使用状态；
* 盘点结果需业务Owner确认。

## Acceptance Criteria

* 关键应用覆盖率达到目标；
* 每个应用有Owner和能力映射；
* 影子IT可见；
* 成本和风险可估算；
* 为重复系统分析提供基础。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
