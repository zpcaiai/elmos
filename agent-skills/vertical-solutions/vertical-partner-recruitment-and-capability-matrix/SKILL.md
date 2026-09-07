---
name: vertical-partner-recruitment-and-capability-matrix
description: "Execute authoritative Batch 17 Skill 664 for vertical partner recruitment and capability matrix. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Vertical Partner Recruitment And Capability Matrix

## Operating contract

Apply authoritative Batch 17 Skill 664. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## 伙伴类型

```text
Industry Consultant
System Integrator
Technology Vendor
Equipment Vendor
Compliance Specialist
Data Specialist
Regional Reseller
Managed Service Provider
```

## Capability Matrix

```yaml
vertical_partner_capability:
  industry: manufacturing
  competencies:
    ot-architecture: advanced
    opc-ua: certified
    migration-platform: certified
    safety: basic
```

## Hard Rules

* 通用平台认证不等于行业认证；
* 高风险行业需领域专家；
* 合规伙伴不能替代技术交付能力；
* 客户数据访问单独批准；
* Partner冲突披露；
* 地区资质需验证；
* 能力定期复审。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
