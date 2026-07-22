---
name: ai-change-release-and-rollback-manager
description: "Execute authoritative Batch 16 Skill 574 for 管理模型、Prompt、Memory、工具、工作流和政策的生产变更。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Ai Change Release And Rollback Manager

## Operating contract

Apply authoritative Batch 16 Skill 574. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理模型、Prompt、Memory、工具、工作流和政策的生产变更。

## Change Unit

```text
Model
Prompt
Tool
Policy
Knowledge
Memory Schema
Workflow
Eval
Autonomy Level
```

## Release Flow

```text
Change Proposal
→ Impact Analysis
→ Eval
→ Security
→ Shadow
→ Canary
→ Approve
→ Deploy
→ Monitor
→ Rollback
```

## Hard Rules

* 变更绑定完整配置Bundle；
* 不能只记录模型名；
* 高风险变更需双人审批；
* Eval失败不得上线；
* Canary期间不扩大权限；
* Rollback包提前准备；
* 紧急变更事后复核。

## Acceptance Criteria

* AI变更可追踪；
* 配置可重现；
* 发布逐步进行；
* Rollback成功；
* 事故率受控；
* 变更影响可量化。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
