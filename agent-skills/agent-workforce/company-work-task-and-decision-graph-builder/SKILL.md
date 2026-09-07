---
name: company-work-task-and-decision-graph-builder
description: "Execute authoritative Batch 16 Skill 528 for 将公司工作拆解为Outcome、流程、任务、决策、知识、工具和例外。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Company Work Task And Decision Graph Builder

## Operating contract

Apply authoritative Batch 16 Skill 528. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

将公司工作拆解为Outcome、流程、任务、决策、知识、工具和例外。

## Work Graph

```text
Company Outcome
→ Business Process
→ Workflow
→ Task
→ Decision
→ Action
→ Evidence
```

## Task Record

```yaml
task:
  task_id: invoice-reconciliation
  outcome: accurate-monthly-close
  frequency: daily
  volume: integer
  current_owner: finance
  tools: []
  data: []
  decisions: []
  exceptions: []
```

## 盘点范围

* 战略；
  -产品；
  -工程；
  -销售；
  -市场；
  -交付；
  -支持；
  -财务；
  -人才；
  -法务；
  -安全；
  -董事会。

## Hard Rules

* 不只盘点文档中的标准流程；
* 实际人工Excel和聊天流程也需识别；
* 决策与执行分开；
* 例外路径必须记录；
* 关系型和情感型工作不能简单任务化；
* Process Owner必须确认；
* 过期流程需废弃。

## Acceptance Criteria

* 关键流程进入Work Graph；
* 决策点可查询；
* 工具和数据依赖明确；
* 隐性人工工作可见；
* 自动化机会可计算；
* 岗位重构有事实基础。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
