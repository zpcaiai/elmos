---
name: ot-plant-and-edge-integration
description: "Execute authoritative Batch 18 Skill 723 for 处理并购后的工厂、设备、边缘和OT环境整合。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Ot Plant And Edge Integration

## Operating contract

Apply authoritative Batch 18 Skill 723. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

处理并购后的工厂、设备、边缘和OT环境整合。

## Hard Rules

* 不强制统一现场控制平台；
* 安全和生产连续优先；
* 设备资产与法人关联；
* 远程访问重新授权；
* OT网络不直接并入IT信任域；
* Edge数据同步有缓冲；
* 工厂整合按现场窗口执行。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
