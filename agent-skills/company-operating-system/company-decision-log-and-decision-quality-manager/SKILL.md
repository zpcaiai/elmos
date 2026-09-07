---
name: company-decision-log-and-decision-quality-manager
description: "Execute authoritative Batch 15 Skill 476 for 记录重大决策的上下文、选项、假设、责任和结果。. Use when Codex must design, operate, review, or verify this Company Operating and Governance System capability."
---

# Company Decision Log And Decision Quality Manager

## Operating contract

Apply authoritative Batch 15 Skill 476. Read [the shared Batch 15 evidence boundary](../references/batch-15-company-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `C15-G` from local implementation evidence.

## Authoritative specification

## Description

记录重大决策的上下文、选项、假设、责任和结果。

## Decision Record

```yaml
decision:
  decision_id: string
  question: 是否进入日本市场
  owner: CEO
  decision_date: string

  options: []
  selected_option: string
  assumptions: []
  risks: []
  reversible: true
  review_date: string
```

## 决策分类

```text
Strategic
Capital
Product
Organization
Hiring
Commercial
Security
Legal
Operational
Board Reserved
```

## Decision Review

在预定日期检查：

* 假设是否成立；
  -结果如何；
  -哪些信息缺失；
  -是否需要修正；
  -决策过程是否改进。

## Hard Rules

* 重大决策不能只保存在聊天或会议中；
* 记录当时信息，避免事后合理化；
* 可逆与不可逆决策采用不同速度；
* Decision Owner明确；
* 董事会保留事项需关联决议；
* 决策记录不能被覆盖；
* 失败决策不用于简单追责。

## Acceptance Criteria

* 重大决策可追溯；
* 决策速度和质量可分析；
* 假设可回测；
* 重复争论减少；
* 董事会和管理层边界清晰；
* 学习进入制度。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
