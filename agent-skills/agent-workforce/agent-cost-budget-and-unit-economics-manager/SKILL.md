---
name: agent-cost-budget-and-unit-economics-manager
description: "Execute authoritative Batch 16 Skill 576 for 管理Agent的模型、计算、工具、人工监督和错误成本。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Cost Budget And Unit Economics Manager

## Operating contract

Apply authoritative Batch 16 Skill 576. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理Agent的模型、计算、工具、人工监督和错误成本。

## Cost Components

```text
Model Tokens
Compute
Tool API
Storage
Human Review
Exceptions
Incidents
Retry
Development
Evaluation
Governance
```

## Unit Economics

```yaml
agent_economics:
  agent_id: support-triage-agent
  cost_per_case: number
  human_baseline_cost: number
  review_cost: number
  error_cost: number
  net_value: number
```

## Hard Rules

* 不能只计算Token成本；
* 人工审查和事故成本纳入；
* 高成本多Agent需证明收益；
* Agent预算有Hard Limit；
* 成本异常自动停止；
* 质量下降不能换取表面成本降低；
* Agent ROI周期复核。

## Acceptance Criteria

* Agent总成本透明；
* 每个Outcome成本可见；
* 与人类基线可比较；
* 低价值Agent退役；
* 预算受控；
* AI投资支持资本配置。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
