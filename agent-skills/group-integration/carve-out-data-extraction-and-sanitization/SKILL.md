---
name: carve-out-data-extraction-and-sanitization
description: "Execute authoritative Batch 18 Skill 726 for 提取目标业务数据并删除不属于交易范围的数据。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Carve Out Data Extraction And Sanitization

## Operating contract

Apply authoritative Batch 18 Skill 726. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

提取目标业务数据并删除不属于交易范围的数据。

## Hard Rules

* 数据按法人、业务和合同筛选；
* 共享记录需字段级处理；
* Legal Hold优先；
* 数据提取有Hash和核对；
* 非交易客户数据不得复制；
* 测试环境同样清理；
* 交付后有销毁证明。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
