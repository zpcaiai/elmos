---
name: recruiting-funnel-and-candidate-operations
description: "Execute authoritative Batch 15 Skill 483 for 管理Sourcing、申请、面试、Offer和入职转换。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Recruiting Funnel And Candidate Operations

## Operating contract

Apply authoritative Batch 15 Skill 483. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

管理Sourcing、申请、面试、Offer和入职转换。

## Funnel

```text
Sourced
→ Contacted
→ Interested
→ Screened
→ Interviewed
→ Final
→ Offer
→ Accepted
→ Started
```

## Metrics

* Time to Fill；
  -Time to Hire；
  -Conversion；
  -Source Quality；
  -Offer Acceptance；
  -Candidate Experience；
  -Diversity；
  -Interview Load；
  -New Hire Performance。

## Hard Rules

* 候选数据遵守隐私；
* 面试反馈需及时；
* Source数量不能代替质量；
* 拒绝原因应结构化；
* 内推不能跳过标准；
* Offer变化需审批；
* 招聘漏斗需按岗位校准。

## Acceptance Criteria

* Pipeline可见；
* 招聘瓶颈可识别；
* 候选体验良好；
* Offer预测准确；
* 渠道质量可分析；
* 招聘结果与入职表现关联。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
