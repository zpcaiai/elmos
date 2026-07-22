---
name: regulatory-control-model-builder
description: "Execute authoritative Batch 17 Skill 597 for 把行业标准、监管条款、合同义务和客户政策转换为统一Control Model。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Regulatory Control Model Builder

## Operating contract

Apply authoritative Batch 17 Skill 597. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

把行业标准、监管条款、合同义务和客户政策转换为统一Control Model。

## Control Schema

```yaml
industry_control:
  control_id: finance.transaction-dual-control
  source_refs: []
  applicability: {}
  objective: string

  requirements:
    - separation-of-duties
    - approval
    - audit

  implementations: []
  tests: []
  evidence: []
```

## Control Categories

```text
Governance
Identity
Access
Data
Change
Audit
Resilience
Safety
Privacy
Transaction
Retention
Incident
Third Party
Model Risk
```

## Hard Rules

* Control不能只有条款摘要；
* Applicability必须明确；
* 法规、标准和客户政策分开；
* Control实现可有多个选择；
* 法律解释不得由模型自动确定；
* Control版本变化需影响分析；
* 未实现Mandatory Control阻止交付。

## Acceptance Criteria

* 监管要求可机器查询；
* Control关联代码和配置；
* Control关联测试和证据；
* 地区差异可覆盖；
* 审计Gap可识别；
* 变更可追踪。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
