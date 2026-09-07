---
name: fundraising-strategy-and-readiness-manager
description: "Execute authoritative Batch 15 Skill 504 for 判断是否融资、融资时点、金额、投资人类型和里程碑。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Fundraising Strategy And Readiness Manager

## Operating contract

Apply authoritative Batch 15 Skill 504. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

判断是否融资、融资时点、金额、投资人类型和里程碑。

## Fundraising Decision

```text
是否必须融资？
融资用于生存还是加速？
融资后达到什么里程碑？
下一轮需要什么证明？
```

## Readiness Dimensions

```text
Market
Product
Revenue
Growth
Retention
Margins
Team
Moat
Financial Controls
Legal
Data Room
Narrative
```

## Raise Amount

需考虑：

* 计划Burn；
  -融资周期；
  -最低Runway；
  -下一里程碑；
  -Downside；
  -费用；
  -预期稀释；
  -是否需要过桥。

## Hard Rules

* 融资不是经营战略的替代；
* 资金用途需具体；
* 不应在现金极度紧张时才启动；
* 估值不是唯一目标；
* 融资计划需考虑管理时间；
* 敏感信息只向合格投资人开放；
* 董事会需批准融资战略。

## Acceptance Criteria

* 融资目的明确；
* 时点合理；
* 金额与里程碑匹配；
* 数据和材料准备；
* 稀释可理解；
* Downside有替代方案。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
