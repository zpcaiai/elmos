---
name: enterprise-risk-management-system
description: "Execute authoritative Batch 15 Skill 516 for 识别、评估、处理和监控全公司战略、财务、运营和合规风险。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Enterprise Risk Management System

## Operating contract

Apply authoritative Batch 15 Skill 516. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

识别、评估、处理和监控全公司战略、财务、运营和合规风险。

## Risk Categories

```text
Strategic
Market
Customer
Product
Technology
AI Model
Cybersecurity
Data
Financial
Liquidity
People
Legal
Regulatory
Partner
Supplier
Reputation
Business Continuity
```

## Risk Record

```yaml
enterprise_risk:
  risk_id: model-provider-dependency
  category: strategic
  likelihood: high
  impact: high
  velocity: medium
  owner: CTO
  treatment: mitigate
  controls: []
```

## Risk Appetite

董事会或管理层定义：

* 可接受；
  -有限接受；
  -极低容忍；
  -零容忍。

例如：

```text
跨Tenant数据泄漏：零容忍
短期产品延迟：有限接受
实验市场失败：可接受
```

## Hard Rules

* 风险需有Owner；
* 风险评价需同时考虑影响和速度；
* Control存在不等于风险已解决；
* 零容忍风险不能普通Waive；
* Top Risk需进入董事会；
* 重大事件后需更新风险；
* Risk Register定期复盘。

## Acceptance Criteria

* 公司Top Risk明确；
* Risk Appetite可执行；
* 控制和缓解措施存在；
* 风险趋势可监控；
* 董事会获得风险透明度；
* 风险影响战略和资本。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
