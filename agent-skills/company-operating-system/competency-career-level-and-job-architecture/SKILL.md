---
name: competency-career-level-and-job-architecture
description: "Execute authoritative Batch 15 Skill 481 for 建立职族、职级、能力、行为和影响范围标准。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Competency Career Level And Job Architecture

## Operating contract

Apply authoritative Batch 15 Skill 481. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立职族、职级、能力、行为和影响范围标准。

## Job Families

```text
Engineering
Product
Design
Sales
Solution Engineering
Delivery
Customer Success
Support
Security
Finance
People
Operations
Legal
```

## Level Dimensions

```text
Scope
Complexity
Autonomy
Impact
Expertise
Leadership
Communication
Judgment
```

## Level Record

```yaml
job_level:
  family: engineering
  level: staff
  expectations:
    scope: cross-team
    impact: company-significant
    autonomy: high
```

## Hard Rules

* 职级不应只由年限决定；
* 管理和专业路径需并行；
* 同级不同职族可有不同能力表现；
* 职级标准用于招聘、绩效和晋升；
* 不能因保留员工随意抬高职级；
* 标准需适应公司阶段；
* 地区差异不改变核心Level含义。

## Acceptance Criteria

* 员工理解成长路径；
* 招聘Level更一致；
* 晋升争议减少；
* 薪酬基准可映射；
* 专业人才不必转管理；
* 职级校准可执行。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
