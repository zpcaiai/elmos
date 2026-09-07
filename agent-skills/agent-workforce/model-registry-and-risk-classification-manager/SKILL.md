---
name: model-registry-and-risk-classification-manager
description: "Execute authoritative Batch 16 Skill 559 for 登记公司使用的所有模型及其用途、风险、部署和Owner。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Model Registry And Risk Classification Manager

## Operating contract

Apply authoritative Batch 16 Skill 559. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

登记公司使用的所有模型及其用途、风险、部署和Owner。

## Model Risk Tiers

```text
R0：无业务影响实验
R1：低风险辅助
R2：内部决策支持
R3：客户或业务执行
R4：高风险、人事、财务、安全或受监管
```

## Model Record

```yaml
model:
  model_id: string
  provider: string
  version: string
  deployment: string
  approved_use_cases: []
  prohibited_use_cases: []
  risk_tier: R2
  owner: string
```

## Hard Rules

* 未登记模型不得正式使用；
* 同一模型不同用例可有不同风险；
* 版本必须精确；
* 模型Deployment和API别名分开；
* 禁止用例明确；
* Owner需负责评测；
* 退役模型有迁移计划。

## Acceptance Criteria

* 模型资产清单完整；
* 用例和风险可查询；
* 未批准模型调用为0；
* 模型版本可追踪；
* 高风险模型有额外控制；
* 模型生命周期受治理。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
