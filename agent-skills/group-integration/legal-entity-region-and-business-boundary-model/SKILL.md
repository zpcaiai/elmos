---
name: legal-entity-region-and-business-boundary-model
description: "Execute authoritative Batch 18 Skill 680 for 定义法人、地区、品牌、数据和合同边界。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Legal Entity Region And Business Boundary Model

## Operating contract

Apply authoritative Batch 18 Skill 680. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

定义法人、地区、品牌、数据和合同边界。

## Boundary Types

```text
Legal Entity
Country
Regulator
Brand
Business Unit
Customer Contract
Data Residency
Tax
Employee
Intellectual Property
```

## Hard Rules

* 法人边界不能仅靠Tenant字段推断；
* 数据和合同义务可能跨系统；
* 跨境处理需专业确认；
* 品牌共享不代表数据可共享；
* 员工和客户数据分开治理；
* 权限必须考虑法人；
* Carve-out资产边界可导出。

## Acceptance Criteria

* 每项资产有法人归属；
* 数据共享有合法依据；
* 地区限制可执行；
* 财务和税务边界明确；
* 分离和整合范围可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
