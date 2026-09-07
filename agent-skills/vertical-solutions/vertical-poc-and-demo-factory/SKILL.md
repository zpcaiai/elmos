---
name: vertical-poc-and-demo-factory
description: "Execute authoritative Batch 17 Skill 662 for 为每个行业建立可信Demo、Sample Data、评测和POC模板。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Vertical Poc And Demo Factory

## Operating contract

Apply authoritative Batch 17 Skill 662. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

为每个行业建立可信Demo、Sample Data、评测和POC模板。

## POC类型

```text
Domain Model POC
Regulatory Evidence POC
Migration Automation POC
Data Migration POC
Behavioral Equivalence POC
Private Deployment POC
```

## POC必须包含

* 代表性业务流程；
  -关键行业Invariant；
  -至少一个控制；
  -至少一个故障路径；
  -业务价值；
  -明确除外项；
  -行业专家验收。

## Hard Rules

* Demo不得使用真实敏感数据；
* POC不等于监管认证；
* 不能只展示Happy Path；
* 行业结论需专家确认；
* POC结果不能无条件外推；
* Sample可重复；
* POC资产可区域本地化。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
