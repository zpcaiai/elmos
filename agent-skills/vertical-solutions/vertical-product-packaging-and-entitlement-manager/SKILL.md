---
name: vertical-product-packaging-and-entitlement-manager
description: "Execute authoritative Batch 17 Skill 610 for 把行业能力打包为SKU、模块、Entitlement和部署Edition。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Vertical Product Packaging And Entitlement Manager

## Operating contract

Apply authoritative Batch 17 Skill 610. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

把行业能力打包为SKU、模块、Entitlement和部署Edition。

## Packaging Example

```text
Finance Core
Finance Payment
Finance Regulatory Evidence
Finance Private Deployment
Finance Migration Factory
```

## Entitlement

```yaml
vertical_entitlement:
  tenant_id: string
  pack_id: healthcare-hospital
  versions: []
  regions: []
  environments: []
```

## Hard Rules

* 客户只能使用购买的行业Pack；
* Regulatory Overlay不可单独脱离Base Pack；
* 高风险Recipe需认证权限；
* Pack版本与支持期限明确；
* 客户私有Extension不进入其他Tenant；
* Packaging不得夸大合规；
* SKU与实际功能一致。

## Acceptance Criteria

* 行业能力可独立销售；
* Entitlement自动执行；
* 版本和地区正确；
* 套餐升级平滑；
* 成本和毛利可计算；
* 合同与部署一致。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
