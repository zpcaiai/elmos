---
name: annual-strategy-and-critical-choice-manager
description: "Execute authoritative Batch 15 Skill 465 for 把长期战略转化为本年度三至五项关键优先级和取舍。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Annual Strategy And Critical Choice Manager

## Operating contract

Apply authoritative Batch 15 Skill 465. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

把长期战略转化为本年度三至五项关键优先级和取舍。

## Annual Priority

```yaml
annual_priority:
  priority_id: enterprise-platform-repeatability
  objective: 建立可重复企业交付能力
  strategic_reason: string
  outcomes: []
  owner: string
  budget: number
```

## 优先级类型

* 产品；
  -市场；
  -销售；
  -交付；
  -组织；
  -财务；
  -融资；
  -风险；
  -区域扩张；
  -生态。

## Resource Constraint

每项优先级必须分配：

* 管理层注意力；
  -Headcount；
  -预算；
  -技术容量；
  -销售容量；
  -时间；
  -董事会支持。

## Hard Rules

* 公司优先级一般不超过五项；
* 无Owner或无预算的优先级无效；
* 每个优先级需有明确牺牲项；
* 优先级冲突由CEO或授权机制解决；
* 季度项目不能自动升级为公司战略；
* 年中改变优先级需正式Replan；
* 年度战略必须影响部门目标。

## Acceptance Criteria

* 年度战略简洁；
* 每项优先级资源充足；
* 员工能够重复说明；
* 部门计划与年度优先级一致；
* 低优先级工作得到削减；
* 结果可季度评估。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
