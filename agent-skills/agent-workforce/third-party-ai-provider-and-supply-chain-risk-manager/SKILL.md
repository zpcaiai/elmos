---
name: third-party-ai-provider-and-supply-chain-risk-manager
description: "Execute authoritative Batch 16 Skill 573 for 管理模型Provider、AI SaaS、开源模型、Agent框架和外部数据供应商风险。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Third Party Ai Provider And Supply Chain Risk Manager

## Operating contract

Apply authoritative Batch 16 Skill 573. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

管理模型Provider、AI SaaS、开源模型、Agent框架和外部数据供应商风险。

## Risk Dimensions

```text
Security
Privacy
Training Use
Residency
Availability
Model Changes
Pricing
Lock-in
License
IP
Subprocessors
Financial Stability
Exit
```

## Provider Record

```yaml
ai_supplier:
  supplier_id: string
  services: []
  approved_data_classes: []
  regions: []
  contractual_controls: []
  exit_plan: {}
```

## Hard Rules

* 供应商合同需覆盖数据使用；
* 单一Provider关键依赖需Fallback；
* 开源模型需验证License和来源；
* Provider变更通知进入流程；
* Subprocessor需可查询；
* 终止时需删除数据；
* 高风险Provider定期复审。

## Acceptance Criteria

* 供应商风险可见；
* 数据政策落实；
* Exit Plan可执行；
* Provider故障有替代；
* License和IP风险受控；
* 第三方变化及时发现。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
