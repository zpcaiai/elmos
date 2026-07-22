---
name: shadow-agent-validation-manager
description: "Execute authoritative Batch 16 Skill 553 for 让Agent观察真实工作并生成建议，但不影响真实结果。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Shadow Agent Validation Manager

## Operating contract

Apply authoritative Batch 16 Skill 553. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

让Agent观察真实工作并生成建议，但不影响真实结果。

## Shadow模式

```text
Human performs work
        +
Agent independently processes same case
        ↓
Compare decision, action and outcome
```

## Shadow Metrics

* 一致率；
  -更好建议率；
  -错误率；
  -遗漏；
  -延迟；
  -成本；
  -例外识别；
  -政策违规。

## Hard Rules

* Shadow Agent不得执行真实写动作；
* Shadow结果不影响员工绩效；
* 生产数据访问需授权；
* 人类结果也不是绝对Golden；
* 差异需专家Review；
* Shadow周期需足够代表性；
* 达标后仍需阶段部署。

## Acceptance Criteria

* 真实分布下评测完成；
* 关键错误被发现；
* 与人类基线可比较；
* 数据安全；
* 达到自主升级门槛；
* 未达标Agent保持Shadow。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
