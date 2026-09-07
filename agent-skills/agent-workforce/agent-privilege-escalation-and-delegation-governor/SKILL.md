---
name: agent-privilege-escalation-and-delegation-governor
description: "Execute authoritative Batch 16 Skill 566 for 防止Agent通过子Agent、工具、工作流或角色组合扩大权限。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Privilege Escalation And Delegation Governor

## Operating contract

Apply authoritative Batch 16 Skill 566. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

防止Agent通过子Agent、工具、工作流或角色组合扩大权限。

## Delegation Chain

```yaml
delegation:
  parent_agent: string
  child_agent: string
  delegated_scope: []
  expires_at: string
```

## Controls

* 权限不超过父Agent；
  -禁止循环委托；
  -限制层级；
  -限制子Agent数量；
  -预算继承；
  -工具继承；
  -数据边界；
  -审批继承。

## Hard Rules

* Agent不能创建更高权限Agent；
* 多个低权限工具组合需分析；
* 临时权限自动过期；
* Delegation需记录；
* 子Agent身份独立；
* Parent被Suspended时子Agent同时停止；
* 人类Owner保持不变或显式变更。

## Acceptance Criteria

* 权限提升攻击被阻止；
* 委托链可查询；
* 无无限Agent生成；
* 预算和权限正确继承；
* 循环委托为0；
* 父Agent停止可传播。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
