---
name: model-evaluation-selection-and-fitness-manager
description: "Execute authoritative Batch 16 Skill 560 for 根据任务、数据、风险、质量、成本和延迟选择模型。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Model Evaluation Selection And Fitness Manager

## Operating contract

Apply authoritative Batch 16 Skill 560. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

根据任务、数据、风险、质量、成本和延迟选择模型。

## Fitness Dimensions

```text
Task Accuracy
Reasoning
Code
Tool Use
Structured Output
Grounding
Safety
Latency
Cost
Context
Residency
Availability
```

## Selection Policy

```text
Policy Compliance
→ Risk Fitness
→ Task Quality
→ Reliability
→ Cost and Latency
```

## Hard Rules

* 最强模型不自动最适合；
* 高风险用例不能只按Benchmark；
* 外部评测和内部任务评测结合；
* 模型选择需考虑数据政策；
* 便宜模型Fallback不能降低安全；
* 模型更换需重跑Agent Eval；
* 多模型路由需可解释。

## Acceptance Criteria

* 每个Agent使用适合模型；
* 质量与成本平衡；
* 高风险用例评测充分；
* 模型Fallback受控；
* 选择决策有证据；
* 模型切换影响可预测。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
