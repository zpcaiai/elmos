---
name: industry-workflow-state-machine-and-invariant-builder
description: "Execute authoritative Batch 17 Skill 602 for 建立行业关键流程、状态转换、时间约束和Invariant。. Use when Codex must design, operate, review, or verify this Vertical Solution Factory capability."
---

# Industry Workflow State Machine And Invariant Builder

## Operating contract

Apply authoritative Batch 17 Skill 602. Read [the shared Batch 17 evidence boundary](../references/batch-17-vertical-solution-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `V17-G` from local implementation evidence.

## Authoritative specification

## Description

建立行业关键流程、状态转换、时间约束和Invariant。

## Workflow Example

```yaml
industry_workflow:
  workflow_id: ecommerce.order
  states:
    - created
    - paid
    - allocated
    - shipped
    - delivered
    - returned

  transitions: []
  invariants: []
```

## Invariant Examples

```text
金融：借贷必须平衡
医疗：用药执行必须有有效医嘱
制造：安全联锁不得被业务流程绕过
电商：退款不得超过已支付金额
通信：计费记录不得无订户或服务关联
```

## Hard Rules

* 状态不能只从代码分支推断；
* 禁止转换显式；
* 补偿和撤销需建模；
* 时间窗口明确；
* 并发转换需定义；
* 关键Invariant进入测试和监控；
* 客户扩展不得破坏基础Invariant。

## Acceptance Criteria

* 关键流程有状态机；
* 非法转换可检测；
* Invariant可自动验证；
* 迁移前后状态可映射；
* 补偿路径完整；
* 生产监控可引用Invariant。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
