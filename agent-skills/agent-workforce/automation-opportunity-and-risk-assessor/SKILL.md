---
name: automation-opportunity-and-risk-assessor
description: "Execute authoritative Batch 16 Skill 529 for 评估任务适合人类、Agent或人机协作。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Automation Opportunity And Risk Assessor

## Operating contract

Apply authoritative Batch 16 Skill 529. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

评估任务适合人类、Agent或人机协作。

## Assessment Dimensions

```text
Repeatability
Rule Clarity
Data Availability
Feedback Speed
Reversibility
Error Impact
Legal Risk
Relationship Requirement
Judgment Requirement
Novelty
Security
```

## Automation Category

```text
human-only
human-led-agent-assisted
agent-led-human-approved
bounded-autonomous
fully-automated-deterministic
not-ready
```

## 高适配任务

* 高频；
  -规则明确；
  -数据结构化；
  -结果可验证；
  -错误可逆；
  -反馈快；
  -例外少。

## 低适配任务

* 重大人事；
  -伦理；
  -法律承诺；
  -高信任关系；
  -危机领导；
  -不可逆决策；
  -目标本身不明确。

## Hard Rules

* 高工时不等于高自动化适配；
* 错误影响必须进入评分；
* 关系型工作价值不能忽略；
* 自动化前先简化流程；
* 无数据任务需先建设数据基础；
* 自动化节省需扣除监督成本；
* 评分需由Process Owner确认。

## Acceptance Criteria

* 每项任务有自动化分类；
* 风险和收益分开；
* 高价值机会获得优先级；
* 不适合自动化任务被保护；
* 自动化项目有明确假设；
* 实际结果可以回测评分。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
