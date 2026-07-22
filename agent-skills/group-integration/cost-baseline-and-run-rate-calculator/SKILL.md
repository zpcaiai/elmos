---
name: cost-baseline-and-run-rate-calculator
description: "Execute authoritative Batch 18 Skill 730 for cost baseline and run rate calculator. Use when Codex must design, operate, review, or verify this Group Integration Factory capability."
---

# Cost Baseline And Run Rate Calculator

## Operating contract

Apply authoritative Batch 18 Skill 730. Read [the shared Batch 18 evidence boundary](../references/batch-18-group-integration-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `M18-H` from local implementation evidence.

## Authoritative specification

## Baseline包括

```text
License
Cloud
Data Center
Vendor
Support
People
Telecom
Facilities
Outsourcing
TSA
```

## Hard Rules

* 合同承诺和当前支出分开；
* 人员成本需考虑重新部署；
* 一次性和Run-rate分开；
* 汇率和税明确；
* 双运行期成本可见；
* Stranded Cost不自动消失；
* 财务部门确认Baseline。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
