---
name: market-customer-and-competitive-intelligence-manager
description: "Execute authoritative Batch 15 Skill 466 for 建立持续更新的市场、客户、竞争和技术情报系统。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Market Customer And Competitive Intelligence Manager

## Operating contract

Apply authoritative Batch 15 Skill 466. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

建立持续更新的市场、客户、竞争和技术情报系统。

## Intelligence Sources

```text
Customer Interviews
Sales Losses
POCs
Support
Usage Data
Partners
Marketplace
Competitors
Industry Reports
Technical Trends
Regulatory Updates
Hiring Data
```

## Intelligence Record

```yaml
intelligence:
  insight_id: string
  domain: competitor
  evidence: []
  confidence: medium
  strategic_implication: string
```

## Competitive Dimensions

* 产品；
  -自动化能力；
  -安全；
  -部署；
  -价格；
  -销售；
  -伙伴；
  -品牌；
  -客户；
  -资金；
  -人才；
  -生态。

## Hard Rules

* 传闻需标记低置信度；
* 竞争信息获取必须合法；
* 销售输单原因需客户证据；
* 单个客户需求不代表市场趋势；
* 情报需要影响决策才能有价值；
* 旧情报需标记过期；
* 地区市场单独分析。

## Acceptance Criteria

* 重要市场变化及时发现；
* 输赢单原因可分析；
* 战略假设得到更新；
* 产品和销售使用统一事实；
* 竞争变化进入董事会材料；
* 情报有Owner和新鲜度。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
