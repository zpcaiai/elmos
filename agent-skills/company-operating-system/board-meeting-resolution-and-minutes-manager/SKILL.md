---
name: board-meeting-resolution-and-minutes-manager
description: "Execute authoritative Batch 15 Skill 520 for 组织董事会会议、Quorum、表决、决议和会议纪要。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Board Meeting Resolution And Minutes Manager

## Operating contract

Apply authoritative Batch 15 Skill 520. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

组织董事会会议、Quorum、表决、决议和会议纪要。

## Meeting Record

```yaml
board_meeting:
  meeting_id: string
  date: string
  attendees: []
  quorum: true
  agenda_items: []
  resolutions: []
```

## Resolution

```yaml
resolution:
  resolution_id: string
  matter: annual-budget
  result: approved
  votes: {}
  conditions: []
```

## Minutes

记录：

* 参会；
  -利益冲突；
  -主要讨论；
  -管理层建议；
  -董事挑战；
  -决议；
  -反对；
  -行动项；
  -附件。

不应逐字记录所有发言。

## Hard Rules

* Quorum和表决符合治理文件；
* 利益冲突董事需按规则回避；
* 书面决议程序需合法；
* Minutes需及时审批；
* 重大决策不得只留在非正式会议；
* 董事会材料和决议关联；
* 法律要求需专业确认。

## Acceptance Criteria

* 会议程序有效；
* 决议可执行；
* Minutes准确；
* 利益冲突处理；
* 行动项明确；
* 法定记录完整。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
