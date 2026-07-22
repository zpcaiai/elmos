---
name: mission-vision-and-operating-principles-builder
description: "Execute authoritative Batch 15 Skill 462 for 定义公司的使命、愿景、长期目标和经营原则。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Mission Vision And Operating Principles Builder

## Operating contract

Apply authoritative Batch 15 Skill 462. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

定义公司的使命、愿景、长期目标和经营原则。

## Mission

回答：

```text
公司为谁解决什么重要问题？
为什么这个问题值得公司长期存在？
```

## Vision

描述三至十年后的目标状态：

* 客户获得什么结果；
  -公司处于什么市场位置；
  -形成什么能力；
  -构建什么生态；
  -对行业产生什么影响。

## Operating Principles

例如：

```text
客户价值优先于功能数量
语义正确性优先于表面自动化
证据优先于主张
可重复系统优先于英雄主义
安全边界优先于短期成交
```

## Hard Rules

* 使命不能只描述产品；
* 愿景不能只是收入数字；
* 原则必须能够指导真实取舍；
* 原则冲突时需要优先级；
* 不能保留从不执行的装饰性价值观；
* 使命和愿景变更需管理层与董事会确认；
* 经营原则需进入招聘、绩效和决策。

## Acceptance Criteria

* 使命清晰；
* 愿景具体；
* 原则可用于决策；
* 员工能够理解；
* 战略和产品与使命一致；
* 原则具有实际案例。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
