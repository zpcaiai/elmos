---
name: investor-profile-and-fundraising-pipeline-manager
description: "Execute authoritative Batch 15 Skill 505 for 建立投资人目标清单、关系、阶段和下一行动。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Investor Profile And Fundraising Pipeline Manager

## Operating contract

Apply authoritative Batch 15 Skill 505. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立投资人目标清单、关系、阶段和下一行动。

## Investor Types

```text
Angel
Seed Fund
Venture Fund
Growth Fund
Strategic Investor
Corporate Venture
Family Office
Debt Provider
Government Fund
```

## Fit Dimensions

* Stage；
  -Check Size；
  -行业；
  -地区；
  -企业软件；
  -AI；
  -开发者工具；
  -董事会价值；
  -竞争冲突；
  -后续能力；
  -声誉。

## Investor Record

```yaml
investor:
  investor_id: string
  fit_score: number
  stage: first-meeting
  champion: string
  concerns: []
  next_action: string
```

## Hard Rules

* 不向明显不匹配投资人浪费时间；
* Strategic Investor需评估商业限制；
* 投资人信息和会议内容保密；
* Pipeline不能只统计Meeting数量；
* 合伙人和基金关系需区分；
* 投资人拒绝原因进入学习；
* 单一投资人依赖需避免。

## Acceptance Criteria

* 目标投资人清单高质量；
* Pipeline状态清晰；
* 每个投资人有Owner；
* 关系和顾虑可追踪；
* 融资预测更真实；
* 反馈可改进Narrative。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
