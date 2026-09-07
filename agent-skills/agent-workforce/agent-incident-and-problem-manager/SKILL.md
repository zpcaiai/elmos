---
name: agent-incident-and-problem-manager
description: "Execute authoritative Batch 16 Skill 558 for 管理Agent错误、越权、失控、数据泄漏和经营损失事件。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Incident And Problem Manager

## Operating contract

Apply authoritative Batch 16 Skill 558. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理Agent错误、越权、失控、数据泄漏和经营损失事件。

## Incident Types

```text
Wrong Decision
Wrong Action
Policy Violation
Data Leak
Privilege Escalation
Runaway Cost
Infinite Loop
Model Drift
Memory Poisoning
Tool Failure
Multi-agent Cascade
```

## Incident Lifecycle

```text
detected
contained
agent-quarantined
impact-assessed
corrected
revalidated
restored
postmortem
closed
```

## Hard Rules

* 严重事故立即Quarantine；
* 保留Prompt、Context、工具和Action证据；
* 不仅修复单次输出，也调查系统原因；
* 数据泄漏进入安全Incident；
* 受影响客户及时通知；
* 恢复前重跑评测；
* Postmortem形成新Guardrail。

## Acceptance Criteria

* Agent事故可快速控制；
* 影响可确定；
* 证据完整；
* 根因可追踪；
* 修复和评测完成；
* 相似事故不重复。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
