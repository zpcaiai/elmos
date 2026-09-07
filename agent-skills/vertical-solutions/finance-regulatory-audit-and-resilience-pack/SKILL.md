---
name: finance-regulatory-audit-and-resilience-pack
description: "Execute authoritative Batch 17 Skill 615 for finance regulatory audit and resilience pack. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Finance Regulatory Audit And Resilience Pack

## Operating contract

Apply authoritative Batch 17 Skill 615. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Control Areas

```text
Operational Resilience
Segregation of Duties
Transaction Audit
Access Review
Data Retention
Change Management
Third-party Risk
Incident Reporting
Payment Data
Business Continuity
```

## Evidence

* 权限矩阵；
  -交易样本；
  -不可变审计；
  -DR测试；
  -对账；
  -变更审批；
  -模型和Agent决策；
  -数据血缘。

## Hard Rules

* 监管Overlay按机构类型和地区配置；
* 不宣称VSP自动实现监管合规；
* Card数据边界单独定义；
* 审计证据绑定生产版本；
* 重大业务服务定义中断容忍度；
* 第三方和模型服务纳入韧性；
* 未解决财务差异阻止Cutover。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
