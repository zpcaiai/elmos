---
name: human-agent-accountability-and-decision-matrix
description: "Execute authoritative Batch 16 Skill 531 for 定义每个业务结果中Human与Agent的责任、执行、审批和监督关系。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Human Agent Accountability And Decision Matrix

## Operating contract

Apply authoritative Batch 16 Skill 531. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

定义每个业务结果中Human与Agent的责任、执行、审批和监督关系。

## HA-RACI

```text
Human Accountable
Human Approver
Agent Responsible
Agent Recommender
Human Reviewer
System Observer
```

## Matrix Record

```yaml
human_agent_matrix:
  process: customer-refund

  agent:
    recommend: true
    prepare: true
    execute_below_amount: false

  human:
    approve: required
    accountable: finance-manager
```

## Human-only Decisions

建议包括：

* 公司战略；
  -董事会事项；
  -融资；
  -股权；
  -高管任免；
  -解雇；
  -重大法律承诺；
  -安全风险豁免；
  -重大客户赔偿；
  -不可逆生产删除。

## Hard Rules

* 每个结果只有明确Human Accountable；
* Agent不能被标记为Accountable；
* 审批不能由同一个Agent模拟；
* 高风险流程需职责分离；
* 矩阵必须映射真实权限；
* 人类审批需提供足够信息；
* Owner离职需重新分配。

## Acceptance Criteria

* 关键流程有责任矩阵；
* 无孤儿Agent；
* 决策权和系统权限一致；
* 高风险事项有人类审批；
* 责任冲突减少；
* 审计能够识别责任人。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
