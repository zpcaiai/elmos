---
name: jurisdiction-regulatory-overlay-manager
description: "Execute authoritative Batch 17 Skill 598 for 把行业基础包与国家、地区、监管机构及客户义务组合。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Jurisdiction Regulatory Overlay Manager

## Operating contract

Apply authoritative Batch 17 Skill 598. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

把行业基础包与国家、地区、监管机构及客户义务组合。

## Overlay

```yaml
regulatory_overlay:
  overlay_id: healthcare-us
  jurisdiction: us
  industry: healthcare

  adds: []
  modifies: []
  prohibits: []
  reporting: []
  retention: []
```

## Overlay Priority

```text
Global Industry Baseline
→ Region
→ Country
→ Sector Regulator
→ Contract
→ Customer Policy
```

下层可以收紧上层要求；放宽Mandatory要求需要合法依据和正式审批。

## Hard Rules

* 不同地区法规不得合并成最低共同标准；
* 监管版本必须记录生效日期；
* 多地区部署需分别评估；
* 客户Policy不能违反法律；
* Overlay冲突需合规人员处理；
* 过期Overlay不得用于新项目；
* 区域渠道只能售卖已就绪Overlay。

## Acceptance Criteria

* 每个Deployment有适用Overlay；
* 控制冲突可发现；
* 数据驻留和保留正确；
* 区域报告可生成；
* 监管更新可影响客户；
* 商业承诺与适用范围一致。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
