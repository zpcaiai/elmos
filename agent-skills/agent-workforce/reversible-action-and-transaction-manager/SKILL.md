---
name: reversible-action-and-transaction-manager
description: "Execute authoritative Batch 16 Skill 546 for 让Agent业务动作具备预览、确认、幂等、补偿和回滚能力。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Reversible Action And Transaction Manager

## Operating contract

Apply authoritative Batch 16 Skill 546. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

让Agent业务动作具备预览、确认、幂等、补偿和回滚能力。

## Action Lifecycle

```text
planned
validated
approved
executing
committed
verified
compensating
rolled-back
failed
```

## Action Record

```yaml
agent_action:
  action_id: string
  idempotency_key: string
  reversible: true
  rollback_action: {}
  before_state: {}
  after_state: {}
```

## Hard Rules

* 写动作需Idempotency Key；
* 提交前捕获Before State；
* 不可逆动作需额外审批；
* 补偿动作本身必须幂等；
* 部分成功必须可识别；
* Agent不得假装回滚外部不可逆动作；
* 回滚后需重新验证。

## Acceptance Criteria

* 重复行动不产生重复副作用；
* 可逆动作可恢复；
* 部分失败可处理；
* 不可逆动作明确标记；
* Action证据完整；
* 回滚成功率可衡量。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
