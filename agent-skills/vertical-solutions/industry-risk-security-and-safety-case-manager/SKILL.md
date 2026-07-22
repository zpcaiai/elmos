---
name: industry-risk-security-and-safety-case-manager
description: "Execute authoritative Batch 17 Skill 609 for 汇总领域风险、控制、测试、残余风险和批准，形成行业Safety或Assurance Case。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Risk Security And Safety Case Manager

## Operating contract

Apply authoritative Batch 17 Skill 609. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

汇总领域风险、控制、测试、残余风险和批准，形成行业Safety或Assurance Case。

## Assurance Chain

```text
Claim
→ Argument
→ Evidence
→ Limitation
→ Residual Risk
→ Approval
```

## Risk Categories

```text
Financial Loss
Patient Harm
Physical Safety
Service Disruption
Privacy
National Security
Consumer Harm
Network Instability
```

## Hard Rules

* 测试通过不能自动证明所有安全；
* Residual Risk显式；
* 高影响Claim需多类证据；
* Safety和Security冲突需共同评估；
* Agent生成论证需专家Review；
* Assurance Case绑定Artifact；
* 重大变化使Case重新评估。

## Acceptance Criteria

* 高风险行业有Assurance Case；
* Claim和证据一致；
* 限制明确；
* 风险获得有权人员批准；
* 审计和客户可复核；
* 上线决策有行业依据。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
