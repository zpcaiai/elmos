---
name: company-okr-architecture-designer
description: "Execute authoritative Batch 15 Skill 470 for 建立公司、功能、团队和个人层面的OKR架构。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Company Okr Architecture Designer

## Operating contract

Apply authoritative Batch 15 Skill 470. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立公司、功能、团队和个人层面的OKR架构。

## OKR层级

```text
Company Outcomes
    ↓
Functional Outcomes
    ↓
Team Outcomes
```

个人绩效不建议直接机械等同OKR得分。

## Objective

应：

* 定性；
  -方向明确；
  -有激励性；
  -与战略相关；
  -在周期内可影响。

## Key Result

应：

* 可衡量；
  -描述结果；
  -有基线；
  -有目标；
  -有Owner；
  -有数据源。

## OKR Record

```yaml
okr:
  objective_id: string
  level: company
  period: 2027-Q1

  objective: 建立可重复的企业POC增长引擎

  key_results:
    - metric: poc-cycle-time
      baseline: 45d
      target: 21d
```

## Hard Rules

* 公司Objective一般不超过五个；
* KR不能只是完成任务；
* 每个KR必须有数据源；
* 不能通过降低质量提升结果；
* BAU指标和突破性OKR分开；
* OKR不能覆盖所有工作；
* OKR中途变更需保留历史。

## Acceptance Criteria

* OKR与年度战略一致；
* KR可自动或可靠计算；
* 团队理解结果；
* 横向依赖明确；
* Guardrail存在；
* 季度可以客观评分。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
