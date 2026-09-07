---
name: identity-cutover-and-rollback-manager
description: "Execute authoritative Batch 18 Skill 697 for 控制身份切换、双目录期和回滚。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Identity Cutover And Rollback Manager

## Operating contract

Apply authoritative Batch 18 Skill 697. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

控制身份切换、双目录期和回滚。

## Hard Rules

* Cutover前验证关键应用；
* 旧身份系统保留受控Fallback；
* 账户创建和禁用在切换窗口冻结或排队；
* Group Delta必须追平；
* 回滚不恢复不应保留的权限；
* Break-glass经过测试；
* 最终身份核对通过。

---

# 七、数据整合Skills

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
