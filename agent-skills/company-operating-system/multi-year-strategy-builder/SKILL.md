---
name: multi-year-strategy-builder
description: "Execute authoritative Batch 15 Skill 464 for 形成三至五年的市场、产品、商业、组织和资本战略。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Multi Year Strategy Builder

## Operating contract

Apply authoritative Batch 15 Skill 464. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

形成三至五年的市场、产品、商业、组织和资本战略。

## Strategy Components

```text
Strategic Ambition
Target Customers
Target Markets
Value Proposition
Winning Model
Product Platform
Distribution
Ecosystem
Operating Model
Capital Strategy
```

## Strategy Choice

```yaml
strategic_choice:
  choice_id: private-runner-enterprise
  decision: 优先赢得高敏感企业客户
  investments: []
  sacrifices: []
  success_conditions: []
```

## 必须明确

* 目标市场；
  -不服务的市场；
  -核心客户；
  -核心问题；
  -差异化；
  -盈利方式；
  -增长方式；
  -护城河；
  -所需能力；
  -资本需求。

## Hard Rules

* 战略必须包含“不做什么”；
* 不能同时追求所有市场和部署模式；
* 战略目标需匹配资本；
* 多年战略需要年度里程碑；
* 战略变化必须说明原因；
* 不能把产品Roadmap当作公司战略；
* 战略须经过压力测试。

## Acceptance Criteria

* 公司方向明确；
* 资源集中；
* 市场和产品选择一致；
* 资本需求可计算；
* 多年结果可衡量；
* 董事会批准战略。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
