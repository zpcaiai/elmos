---
name: capital-allocation-and-investment-committee-manager
description: "Execute authoritative Batch 15 Skill 503 for 管理重大产品、市场、人才、基础设施和并购投资决策。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Capital Allocation And Investment Committee Manager

## Operating contract

Apply authoritative Batch 15 Skill 503. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

管理重大产品、市场、人才、基础设施和并购投资决策。

## Investment Proposal

```yaml
investment:
  investment_id: japan-market-entry
  amount: number
  strategic_fit: high
  expected_outcomes: []
  scenarios: []
  risks: []
  stage_gates: []
```

## Evaluation Dimensions

* 战略适配；
  -客户价值；
  -经济回报；
  -现金；
  -风险；
  -组织能力；
  -可逆性；
  -机会成本；
  -学习价值。

## Stage Funding

大型投资采用：

```text
Discovery
→ Pilot
→ Scale
```

而不是一次性投入全部资本。

## Hard Rules

* 沉没成本不应支配继续投入；
* 所有重大投资需有停止条件；
* 资金使用需有里程碑；
* 机会成本需明确；
* CEO和董事会权限边界清晰；
* 未实现收益需复盘；
* 资本配置记录可审计。

## Acceptance Criteria

* 资本投向战略重点；
* 低价值投入及时停止；
* 重大投资分阶段；
* 现金风险可控；
* 投资回报可复盘；
* 董事会获得透明度。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
