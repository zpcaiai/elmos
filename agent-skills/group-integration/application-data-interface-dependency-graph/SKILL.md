---
name: application-data-interface-dependency-graph
description: "Execute authoritative Batch 18 Skill 676 for 建立应用、数据、身份、消息、用户和外部合作方的集团依赖图。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Application Data Interface Dependency Graph

## Operating contract

Apply authoritative Batch 18 Skill 676. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

建立应用、数据、身份、消息、用户和外部合作方的集团依赖图。

## Edge Types

```text
API Call
Database Read/Write
Message Produce/Consume
File Transfer
Identity Dependency
Shared Library
Batch Dependency
Operational Dependency
Contractual Dependency
```

## Hard Rules

* 直接数据库访问必须识别；
* 隐式时间依赖需记录；
* 共享文件和人工导入不可忽略；
* 每条关键依赖有Owner；
* 依赖图包含方向和Criticality；
* 图谱需基于运行流量校验；
* 退役前重新扫描。

## Acceptance Criteria

* 关键应用依赖完整；
* Wave和Cutover可基于图谱规划；
* 隐藏调用方减少；
* 共享平台单点可见；
* 退役风险可计算。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
