---
name: uncertainty-hallucination-and-evidence-validator
description: "Execute authoritative Batch 16 Skill 563 for 要求Agent表达不确定性，并对事实、计算和业务结果进行验证。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Uncertainty Hallucination And Evidence Validator

## Operating contract

Apply authoritative Batch 16 Skill 563. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

要求Agent表达不确定性，并对事实、计算和业务结果进行验证。

## Confidence Types

```text
Model Confidence
Evidence Coverage
Data Quality
Rule Certainty
Outcome Verification
```

不应将模型自报置信度视为真实概率。

## Validation Methods

* 数据库查询；
  -确定性计算；
  -Schema；
  -外部权威源；
  -业务规则；
  -第二模型；
  -人工专家；
  -实际执行结果；
  -历史基线。

## Hard Rules

* 无证据事实不得进入高风险行动；
* 引用必须对应真实来源；
* 不确定时应升级而非编造；
* 数字需确定性计算；
* 第二模型一致不等于事实正确；
* 关键输出需Verifier；
* 幻觉事件进入Eval Corpus。

## Acceptance Criteria

* Agent不隐藏不确定性；
* 高风险事实有证据；
* 计算准确；
* 引用可验证；
* 幻觉率可衡量；
* 错误发现后形成回归测试。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
