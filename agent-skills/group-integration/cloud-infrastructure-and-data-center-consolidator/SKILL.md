---
name: cloud-infrastructure-and-data-center-consolidator
description: "Execute authoritative Batch 18 Skill 685 for 规划云账号、区域、数据中心、主机、网络和基础设施收敛。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Cloud Infrastructure And Data Center Consolidator

## Operating contract

Apply authoritative Batch 18 Skill 685. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

规划云账号、区域、数据中心、主机、网络和基础设施收敛。

## Disposition

```text
Retain
Migrate
Consolidate
Exit
Rehost
Replatform
Colocate
Isolate
```

## Hard Rules

* 数据中心退出需先完成依赖验证；
* 网络延迟和数据驻留进入设计；
* 云账号合并不能破坏Billing和权限；
* 共享基础设施需Tenant和法人隔离；
* Contract和Reserved Capacity进入成本；
* 迁移期间保持DR；
* 删除资产前确认Backup。

## Acceptance Criteria

* 基础设施目标拓扑明确；
* 数据中心退出日期可追踪；
* 云成本和合同可见；
* 迁移Wave与应用一致；
* Stranded Infrastructure可移除。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
