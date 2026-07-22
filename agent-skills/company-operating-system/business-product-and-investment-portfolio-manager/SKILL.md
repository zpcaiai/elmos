---
name: business-product-and-investment-portfolio-manager
description: "Execute authoritative Batch 15 Skill 468 for 管理产品线、市场、地区、商业模式和长期投资组合。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Business Product And Investment Portfolio Manager

## Operating contract

Apply authoritative Batch 15 Skill 468. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

管理产品线、市场、地区、商业模式和长期投资组合。

## Portfolio Categories

```text
Core Business
Growth Business
Strategic Option
Research
Maintenance
Sunset
```

## Portfolio Record

```yaml
portfolio_item:
  item_id: air-gapped-edition
  category: growth-business
  investment: number
  expected_return: number
  strategic_fit: high
  risk: medium
```

## Evaluation Dimensions

* 战略适配；
  -市场；
  -收入；
  -毛利；
  -客户需求；
  -技术杠杆；
  -风险；
  -资本；
  -组织复杂度；
  -机会成本。

## Hard Rules

* 过去投入不能成为继续投入的唯一理由；
* 每个项目需有停止条件；
* Research与Committed Revenue分开；
* Sunset项目需客户迁移计划；
* 组合不能超过组织承载能力；
* CEO宠爱项目也需统一评估；
* 资本配置结果需董事会可见。

## Acceptance Criteria

* 所有重大投入有分类；
* 低价值项目能够停止；
* 核心业务获得足够资源；
* 战略Option受控；
* 组合风险可理解；
* 资金使用与战略一致。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
