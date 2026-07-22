---
name: agent-output-action-and-anomaly-monitor
description: "Execute authoritative Batch 16 Skill 568 for 监控Agent输出、工具调用、预算、速度和业务结果中的异常。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Output Action And Anomaly Monitor

## Operating contract

Apply authoritative Batch 16 Skill 568. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

监控Agent输出、工具调用、预算、速度和业务结果中的异常。

## Anomaly Types

```text
Sudden Action Increase
Unusual Customer Scope
Large Spend
Repeated Retries
Output Pattern Change
Tool Sequence Change
Data Volume Change
Night-time Activity
High Rejection
Unexpected External Domain
```

## Controls

* 规则；
  -统计；
  -基线；
  -模型；
  -业务Invariant；
  -人工抽检。

## Hard Rules

* 异常检测不能替代硬权限；
* 高风险异常实时阻断；
* 告警需有Owner；
* Agent不能关闭自己的监控；
* 误报需持续优化；
* 异常关联模型和版本；
* 监控数据遵守隐私。

## Acceptance Criteria

* 重大异常及时发现；
* Runaway Cost可阻止；
* 越界客户范围可识别；
* 告警噪声受控；
* 调查证据完整；
* 异常形成新Eval。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
