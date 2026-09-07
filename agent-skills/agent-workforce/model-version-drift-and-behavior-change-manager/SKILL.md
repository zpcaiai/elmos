---
name: model-version-drift-and-behavior-change-manager
description: "Execute authoritative Batch 16 Skill 567 for 监控模型、Prompt、数据和工具变化导致的Agent行为漂移。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Model Version Drift And Behavior Change Manager

## Operating contract

Apply authoritative Batch 16 Skill 567. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

监控模型、Prompt、数据和工具变化导致的Agent行为漂移。

## Drift Sources

```text
Model Upgrade
Provider Change
Prompt Change
Retrieval Change
Knowledge Change
Tool Change
Policy Change
Data Distribution Change
User Behavior Change
```

## Drift Metrics

* Eval变化；
  -拒绝率；
  -Override率；
  -异常率；
  -成本；
  -工具选择；
  -行动分布；
  -业务Outcome；
  -安全事件。

## Hard Rules

* Provider静默模型更新需检测；
* 模型Alias不作为稳定版本；
* Drift超阈值自动降级；
* 新版本使用Canary；
* 历史输入需重放；
* 行为变化需解释；
* Drift事件进入Risk Register。

## Acceptance Criteria

* 漂移及时发现；
* 模型版本可辨识；
* Canary和Rollback有效；
* 业务影响可测；
* 高风险Agent自动限制；
* 基线持续更新。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
