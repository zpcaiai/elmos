---
name: fundraising-data-room-manager
description: "Execute authoritative Batch 15 Skill 507 for 组织融资所需公司、财务、法律、产品、客户和安全资料。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Fundraising Data Room Manager

## Operating contract

Apply authoritative Batch 15 Skill 507. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

组织融资所需公司、财务、法律、产品、客户和安全资料。

## Data Room Sections

```text
Corporate
Cap Table
Financials
Tax
Contracts
Customers
Pipeline
Product
Technology
Security
Intellectual Property
People
Litigation
Insurance
Policies
Board
```

## Access

* 投资人；
  -阶段；
  -文件；
  -过期；
  -水印；
  -下载；
  -审计。

## Hard Rules

* 不向所有投资人开放完整客户合同；
* PII和Secret必须处理；
* 材料使用最新批准版本；
* Cap Table和财务数字一致；
* 重大风险不得隐藏；
* Access可撤销；
* 文件更新保留版本。

## Acceptance Criteria

* 尽调资料完整；
* 权限受控；
* 文件新鲜；
* 投资人问题减少；
* 风险披露一致；
* Access可审计。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
