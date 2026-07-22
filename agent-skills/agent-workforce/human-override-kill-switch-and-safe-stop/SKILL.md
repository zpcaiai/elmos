---
name: human-override-kill-switch-and-safe-stop
description: "Execute authoritative Batch 16 Skill 557 for 提供单Action、单Agent、Agent Team、工具和全公司级停止机制。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Human Override Kill Switch And Safe Stop

## Operating contract

Apply authoritative Batch 16 Skill 557. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

提供单Action、单Agent、Agent Team、工具和全公司级停止机制。

## Stop Levels

```text
Cancel Action
Pause Job
Suspend Agent
Quarantine Agent Team
Disable Tool
Revoke Credentials
Disable Model
Freeze Autonomous Operations
```

## Safe Stop

停止时需：

* 停止新动作；
  -等待或取消在途动作；
  -保留状态；
  -撤销Credential；
  -记录证据；
  -执行补偿；
  -通知Owner。

## Hard Rules

* Kill Switch不依赖被停Agent；
* 停止权限属于明确人类角色；
* 停止机制定期演练；
* 不能只关闭UI；
* 不可安全取消动作需明确；
* 全局Freeze需保护关键业务连续性；
* 恢复需重新审批。

## Acceptance Criteria

* 各级停止有效；
* Credential同步撤销；
* 在途动作安全处理；
* 演练通过；
* 停止有审计；
* 恢复流程明确。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
