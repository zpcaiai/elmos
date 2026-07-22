---
name: structured-interview-and-hiring-scorecard-manager
description: "Execute authoritative Batch 15 Skill 484 for 通过结构化面试和独立评分提高招聘决策质量。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Structured Interview And Hiring Scorecard Manager

## Operating contract

Apply authoritative Batch 15 Skill 484. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

通过结构化面试和独立评分提高招聘决策质量。

## Scorecard

```yaml
hiring_scorecard:
  role_id: migration-architect
  outcomes: []
  competencies:
    - system-design
    - migration-experience
    - customer-communication
    - judgment
```

## Interview Design

每轮面试明确：

* 评估能力；
  -问题；
  -证据；
  -评分锚点；
  -面试官；
  -时间；
  -禁止重复。

## Decision

应基于：

```text
Role Scorecard
+ Evidence
+ Reference
+ Risks
```

而不是“感觉不错”。

## Hard Rules

* 面试官在讨论前独立提交反馈；
* 禁止与岗位无关的歧视性问题；
* 评分必须有证据；
* Culture Add优于模糊Culture Fit；
* 关键岗位需Reference；
* 强力支持者不能覆盖Critical Red Flag；
* 招聘决策可审计。

## Acceptance Criteria

* 面试结构一致；
* 评分可比较；
* 偏见降低；
* 面试效率提高；
* 招聘质量可回测；
* 候选人获得公平体验。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
