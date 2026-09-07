---
name: autonomy-promotion-and-demotion-controller
description: "Execute authoritative Batch 16 Skill 554 for 根据评测、生产表现和风险调整Agent自主等级。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Autonomy Promotion And Demotion Controller

## Operating contract

Apply authoritative Batch 16 Skill 554. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

根据评测、生产表现和风险调整Agent自主等级。

## Promotion Conditions

```text
Eval Pass
Shadow Pass
Low Exception Rate
No Critical Policy Violation
Rollback Verified
Human Owner Approval
Stable Model Version
```

## Demotion Triggers

* 事故；
  -漂移；
  -异常输出；
  -政策变化；
  -模型变化；
  -高Override；
  -客户投诉；
  -成本异常；
  -Owner缺失。

## Hard Rules

* 自主等级不能由Agent自行提高；
* 每次只提高一级；
* 高风险用例需更长观察；
* Demotion必须即时生效；
* Promotion绑定Agent和模型版本；
* 权限同步调整；
* 等级定期重新认证。

## Acceptance Criteria

* 自主权渐进提高；
* 风险变化及时降级；
* Promotion有证据；
* 权限与等级一致；
* Agent事故后可快速限制；
* 高自主Agent持续复核。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
