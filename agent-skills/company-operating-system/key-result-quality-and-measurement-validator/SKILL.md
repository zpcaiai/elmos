---
name: key-result-quality-and-measurement-validator
description: "Execute authoritative Batch 15 Skill 472 for 检查KR是否可衡量、可影响、无操纵空间且具有正确Guardrail。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Key Result Quality And Measurement Validator

## Operating contract

Apply authoritative Batch 15 Skill 472. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

检查KR是否可衡量、可影响、无操纵空间且具有正确Guardrail。

## KR质量检查

```text
Outcome not Output
Clear Formula
Defined Population
Reliable Data
Controllable
Time-bound
Baseline
Target
No Perverse Incentive
Guardrails
```

## 低质量KR示例

```text
完成新网站
发布20篇文章
招聘10个人
举办5场活动
```

这些通常是Output或Initiative。

更好的KR：

```text
Qualified Assessment转化率从8%提升到15%
关键岗位平均招聘周期从75天降至50天
```

## Hard Rules

* 无基线KR需说明；
* 无Owner KR无效；
* 数据不可用需先建Measurement；
* 不能使用可轻易操纵指标；
* 质量、安全和毛利需作为Guardrail；
* 团队不能在期末修改公式；
* KR定义变化需重置比较。

## Acceptance Criteria

* KR描述结果；
* 数据口径清晰；
* 目标具有挑战但可影响；
* Manipulation风险受控；
* Guardrail完整；
* 评分可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
