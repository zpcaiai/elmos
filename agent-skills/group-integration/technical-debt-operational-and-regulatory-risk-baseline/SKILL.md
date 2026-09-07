---
name: technical-debt-operational-and-regulatory-risk-baseline
description: "Execute authoritative Batch 18 Skill 682 for 建立交易后统一风险基线。. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Technical Debt Operational And Regulatory Risk Baseline

## Operating contract

Apply authoritative Batch 18 Skill 682. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Description

建立交易后统一风险基线。

## Risk Domains

```text
EOL Technology
Unsupported Software
Security Vulnerability
Single Point of Failure
Manual Process
Missing Tests
Data Quality
Regulatory Gap
Key-person Risk
Vendor Lock-in
```

## Hard Rules

* 风险需区分继承风险和整合新增风险；
* 高风险资产不能因即将退役而忽略；
* 退役时间过长需临时缓解；
* 风险Owner明确；
* 财务影响可估算；
* 重大风险进入Day 1或Day 100；
* 风险关闭需证据。

## Acceptance Criteria

* 高风险应用和依赖可见；
* 迁移Wave考虑风险；
* 短期缓解和长期方案分开；
* 管理层理解技术风险；
* 风险影响协同模型。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
