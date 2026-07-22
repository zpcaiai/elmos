---
name: agent-provisioning-lifecycle-manager
description: "Execute authoritative Batch 16 Skill 536 for 管理Agent创建、评测、批准、部署、升级、暂停和退役。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Provisioning Lifecycle Manager

## Operating contract

Apply authoritative Batch 16 Skill 536. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理Agent创建、评测、批准、部署、升级、暂停和退役。

## Lifecycle

```text
requested
designed
implemented
evaluating
shadow
approved
active
restricted
quarantined
retiring
retired
```

## Provisioning Flow

1. 提交Business Case。
2. 创建Charter。
3. 分配Human Owner。
4. 分配风险等级。
5. 构建Agent。
6. 离线评测。
7. 安全评测。
8. Shadow运行。
9. 审批。
10. 分阶段部署。
11. 持续监控。
12. 周期复核。

## Hard Rules

* 创建Agent需业务Owner；
* Agent升级不得覆盖旧版本记录；
* 模型变化需重新评测；
* 长期无使用Agent需退役；
* 事故Agent自动Quarantine；
* 退役前撤销工具和Credential；
* Agent资产不得私自复制。

## Acceptance Criteria

* 生命周期合法；
* 未批准Agent不能生产执行；
* 版本清晰；
* Quarantine有效；
* 退役无残留权限；
* Agent Portfolio保持整洁。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
