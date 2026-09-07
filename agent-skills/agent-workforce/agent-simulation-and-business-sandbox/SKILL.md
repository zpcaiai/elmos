---
name: agent-simulation-and-business-sandbox
description: "Execute authoritative Batch 16 Skill 552 for 在隔离环境中模拟Agent与流程、人员、客户和系统的互动。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Agent Simulation And Business Sandbox

## Operating contract

Apply authoritative Batch 16 Skill 552. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

在隔离环境中模拟Agent与流程、人员、客户和系统的互动。

## Simulation Types

```text
Synthetic Tasks
Historical Replay
Digital Customer
Tool Simulator
Failure Injection
Multi-agent Scenario
Market Scenario
Crisis Exercise
```

## Sandbox限制

* 无生产写入；
  -测试Credential；
  -合成或脱敏数据；
  -虚拟时间；
  -虚拟预算；
  -外部服务模拟；
  -完整Trace。

## Hard Rules

* Simulation结果不能替代生产验证；
* 模拟器假设需公开；
* 高风险场景需包含故障；
* Agent不能识别并利用测试漏洞；
* Sandbox与生产权限分开；
* 模拟数据遵守隐私；
* Simulation需可重复。

## Acceptance Criteria

* 新Agent可安全训练和评测；
* 极端场景可测试；
* 事故前发现问题；
* 经营策略可比较；
* 模拟与真实结果偏差可分析；
* Sandbox成本可控。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
