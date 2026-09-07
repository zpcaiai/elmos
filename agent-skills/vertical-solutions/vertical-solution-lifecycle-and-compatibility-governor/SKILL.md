---
name: vertical-solution-lifecycle-and-compatibility-governor
description: "Execute authoritative Batch 17 Skill 612 for 管理行业标准、控制、Recipe、架构、评测和商业版本生命周期。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Vertical Solution Lifecycle And Compatibility Governor

## Operating contract

Apply authoritative Batch 17 Skill 612. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

管理行业标准、控制、Recipe、架构、评测和商业版本生命周期。

## Lifecycle

```text
Research
→ Design Partner
→ Candidate
→ Certified
→ Commercial
→ Maintenance
→ Deprecated
→ Retired
```

## Change Triggers

* 监管更新；
  -标准更新；
  -行业事故；
  -新技术；
  -产品版本；
  -客户反馈；
  -漏洞；
  -市场变化。

## Hard Rules

* 标准更新不直接自动修改生产控制；
* Impact Analysis必须执行；
* 客户通知和过渡期明确；
* 旧版本支持期限明确；
* 紧急安全更新可加速但需复核；
* Deprecated Pack不能用于新项目；
* 退役需提供迁移路径。

## Acceptance Criteria

* 行业版本持续更新；
* 兼容性影响可查；
* 客户升级可计划；
* 监管变化及时处理；
* 资产维护责任清晰；
* 无永久过时Pack。

---

# 六、金融行业包

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
