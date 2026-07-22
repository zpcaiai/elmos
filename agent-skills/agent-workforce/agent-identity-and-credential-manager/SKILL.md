---
name: agent-identity-and-credential-manager
description: "Execute authoritative Batch 16 Skill 535 for 为每个Agent提供独立身份、短期Credential和可撤销访问。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Identity And Credential Manager

## Operating contract

Apply authoritative Batch 16 Skill 535. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

为每个Agent提供独立身份、短期Credential和可撤销访问。

## Agent Identity

```yaml
agent_identity:
  agent_id: string
  principal_id: string
  owner_id: string
  tenant_id: string
  allowed_audiences: []
```

## Credential要求

* 短期；
  -任务绑定；
  -工具绑定；
  -最小Scope；
  -不可转让；
  -可撤销；
  -自动轮换；
  -完整审计。

## Hard Rules

* 不共享员工Credential；
* Agent之间不共享高权限Token；
* Credential不得进入Memory；
* 身份被Quarantine后立即撤销；
* Agent调用必须显示Agent ID；
* 代理人和Human Owner均进入审计；
* 开发和生产身份分开。

## Acceptance Criteria

* 每个行动可识别Agent；
* Credential自动轮换；
* 跨Agent权限滥用为0；
* Owner变化可更新；
* 撤销实时生效；
* 无长期共享密钥。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
