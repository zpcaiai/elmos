---
name: corporate-governance-architecture-builder
description: "Execute authoritative Batch 15 Skill 513 for 建立股东、董事会、管理层和委员会的权责结构。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Corporate Governance Architecture Builder

## Operating contract

Apply authoritative Batch 15 Skill 513. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立股东、董事会、管理层和委员会的权责结构。

## Governance Layers

```text
Shareholders
Board
Board Committees
CEO
Executive Team
Management Committees
Functional Leadership
```

## Governance Documents

* 公司章程；
  -股东协议；
  -董事会议事规则；
  -委员会章程；
  -授权矩阵；
  -利益冲突政策；
  -签字权限；
  -信息权；
  -保留事项。

## Hard Rules

* 法定要求需专业法律确认；
* 董事会监督与管理执行分开；
* 管理层不能绕过保留事项；
* 股东权利按协议执行；
* 治理文件版本化；
* 委员会不能替代董事会法定责任；
* 实际运作需与文件一致。

## Acceptance Criteria

* 治理结构清晰；
* 权限和责任明确；
* 法定程序可执行；
* 融资条款被落实；
* 决策路径高效；
* 治理资料可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
