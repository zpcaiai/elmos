---
name: agent-autonomy-and-authority-envelope-manager
description: "Execute authoritative Batch 16 Skill 534 for 定义Agent在金额、资源、客户、工具、时间和行为上的授权范围。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Autonomy And Authority Envelope Manager

## Operating contract

Apply authoritative Batch 16 Skill 534. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

定义Agent在金额、资源、客户、工具、时间和行为上的授权范围。

## Authority Envelope

```yaml
authority_envelope:
  agent_id: procurement-agent

  spend:
    max_per_action: 500
    max_per_day: 2000

  vendors:
    allowlisted: []

  actions:
    create-draft-order: true
    submit-order: false

  validity:
    start: string
    end: string
```

## Envelope Dimensions

* 金额；
  -次数；
  -时间；
  -地区；
  -Tenant；
  -客户；
  -数据；
  -工具；
  -对象；
  -风险；
  -并发；
  -子Agent；
  -外部通信。

## Hard Rules

* 默认最小授权；
* 权限必须自动过期或定期复核；
* Agent不能修改自己的Envelope；
* 子Agent权限不能超过父Agent；
* 金额拆分不能规避限制；
* 超限动作必须失败或升级；
* Envelope变化需审计。

## Acceptance Criteria

* Agent只能在Envelope内行动；
* 超限无法绕过；
* 权限和Charter一致；
* 临时授权自动过期；
* 子Agent权限受控；
* 高风险动作正确升级。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
