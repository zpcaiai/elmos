---
name: ai-audit-evidence-and-provenance-manager
description: "Execute authoritative Batch 16 Skill 575 for 记录Agent从目标、上下文、模型、计划、工具到结果的完整证据链。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Ai Audit Evidence And Provenance Manager

## Operating contract

Apply authoritative Batch 16 Skill 575. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

记录Agent从目标、上下文、模型、计划、工具到结果的完整证据链。

## Provenance Chain

```text
Company Objective
→ Workflow
→ Agent
→ Model
→ Prompt
→ Context
→ Plan
→ Tool Calls
→ Actions
→ Validation
→ Outcome
→ Human Decisions
```

## Hard Rules

* 高风险Action必须完整Trace；
* Secret不得进入审计明文；
* Human Override记录；
* 模型和Prompt版本精确；
* Evidence不可被Agent修改；
* 审计保留遵守政策；
* 支持独立复现。

## Acceptance Criteria

* 任意行动可追溯；
* 人机责任清晰；
* 决策证据完整；
* 事故调查可执行；
* 审计防篡改；
* 合规报告可生成。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
