---
name: okr-cascade-and-cross-functional-alignment
description: "Execute authoritative Batch 15 Skill 471 for 使公司OKR与各部门目标纵向关联，并解决跨部门目标冲突。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Okr Cascade And Cross Functional Alignment

## Operating contract

Apply authoritative Batch 15 Skill 471. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

使公司OKR与各部门目标纵向关联，并解决跨部门目标冲突。

## Alignment Types

```text
Direct Contribution
Shared Outcome
Dependency
Guardrail
Supporting Metric
```

## Alignment Record

```yaml
okr_alignment:
  parent_kr: company.poc-cycle-time
  child_okr: delivery.standard-poc
  contribution_type: direct
  contribution_weight: 0.4
```

## 横向协调

典型冲突：

* 销售追求签约，交付追求毛利；
  -产品追求速度，安全追求控制；
  -增长追求注册，支持承担工单；
  -模型质量提升，成本恶化。

## Hard Rules

* 部门不得创建与公司目标冲突的KR；
* Shared KR需要单一最终Owner；
* Dependency需有承诺日期；
* 部门局部最优不得破坏公司结果；
* 所有KR无需强行级联；
* 共同目标需清晰责任；
* 冲突需在季度开始前解决。

## Acceptance Criteria

* 公司目标得到功能支持；
* 跨部门依赖可见；
* Shared Outcome有Owner；
* 局部激励冲突减少；
* 资源冲突可升级；
* OKR地图可视化。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
