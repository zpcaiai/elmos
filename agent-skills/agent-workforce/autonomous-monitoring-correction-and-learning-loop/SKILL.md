---
name: autonomous-monitoring-correction-and-learning-loop
description: "Execute authoritative Batch 16 Skill 589 for 持续监控目标和结果，在授权范围内自动纠偏，并把经验回写系统。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Autonomous Monitoring Correction And Learning Loop

## Operating contract

Apply authoritative Batch 16 Skill 589. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

持续监控目标和结果，在授权范围内自动纠偏，并把经验回写系统。

## Loop

```text
Observe Metrics
→ Detect Variance
→ Diagnose
→ Select Corrective Action
→ Check Policy
→ Execute or Request Approval
→ Verify
→ Update Knowledge
```

## 可自主纠偏

例如：

* 调整低风险队列；
  -重试可幂等任务；
  -暂停异常Campaign；
  -降低Agent并发；
  -切换批准模型；
  -创建调查任务；
  -回滚低风险配置。

## Hard Rules

* 纠偏必须有明确目标；
* 不得通过修改指标消除偏差；
* 高风险纠偏需审批；
* 重复纠偏无效时停止；
* 所有变化可回滚；
* 学习写入需验证；
* 纠偏效果必须复核。

## Acceptance Criteria

* 偏差发现更快；
* 低风险问题自动恢复；
* 人工只处理关键例外；
* 纠偏不会振荡；
* 学习进入流程和Eval；
* 经营结果持续改善。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
