---
name: unit-economics-and-contribution-margin-manager
description: "Execute authoritative Batch 15 Skill 497 for 计算客户、产品、项目、渠道和部署模式的单位经济。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Unit Economics And Contribution Margin Manager

## Operating contract

Apply authoritative Batch 15 Skill 497. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

计算客户、产品、项目、渠道和部署模式的单位经济。

## Metrics

```text
Gross Margin
Contribution Margin
CAC
LTV
Payback
NRR
Support Cost per Customer
Model Cost per Run
Runner Cost per Migration
Delivery Cost per Repository
Marketplace Take Rate
```

## Contribution Margin

```text
Revenue
- Direct Cloud and Model
- Direct Support
- Direct Delivery
- Partner Share
- Payment Cost
= Contribution Margin
```

## Hard Rules

* 不同业务模式分开分析；
* 服务毛利不能掩盖软件毛利；
* 高收入客户可能贡献毛利为负；
* CAC需包括POC和方案成本；
* LTV基于毛利而非收入；
* 模型成本异常需及时处理；
* 单位经济需按Region和Channel拆分。

## Acceptance Criteria

* 产品和客户盈利性可见；
* 低毛利原因可识别；
* 定价可以调整；
* 增长投入有经济依据；
* 续费和扩张价值可量化；
* 董事会可理解商业模型。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
