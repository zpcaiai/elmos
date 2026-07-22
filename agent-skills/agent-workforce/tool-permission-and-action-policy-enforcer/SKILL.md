---
name: tool-permission-and-action-policy-enforcer
description: "Execute authoritative Batch 16 Skill 542 for 在每次Agent工具调用前执行身份、资源、参数和上下文政策。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Tool Permission And Action Policy Enforcer

## Operating contract

Apply authoritative Batch 16 Skill 542. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

在每次Agent工具调用前执行身份、资源、参数和上下文政策。

## Policy Input

```yaml
action_request:
  agent_id: string
  human_owner: string
  tool_id: string
  resource: {}
  parameters: {}
  budget_state: {}
  risk_context: {}
```

## Policy检查

* Agent身份；
  -Charter；
  -Authority Envelope；
  -数据范围；
  -时间；
  -金额；
  -审批；
  -风险；
  -当前Agent状态；
  -用户和Tenant政策。

## Hard Rules

* 每次工具调用实时检查；
* UI或Prompt中的授权声明无效；
* Agent不能修改Policy；
* Policy失败默认拒绝；
* 参数级限制必须执行；
* Approval绑定具体Action Hash；
* Policy决定进入审计。

## Acceptance Criteria

* 越权工具调用为0；
* 参数拆分无法绕过限制；
* 审批与Action一致；
* Policy性能满足运行要求；
* 决策可解释；
* 紧急撤销即时生效。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
