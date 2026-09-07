---
name: company-knowledge-graph-and-semantic-layer
description: "Execute authoritative Batch 16 Skill 540 for 将战略、产品、客户、流程、指标、政策和人员知识形成可供Human和Agent共同使用的语义层。. Use when Codex must design, operate, review, or verify this AI-native company and Agent Workforce capability."
---

# Company Knowledge Graph And Semantic Layer

## Operating contract

Apply authoritative Batch 16 Skill 540. Read [the shared Batch 16 evidence boundary](../references/batch-16-agent-workforce-evidence-boundary.md) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `AI16-G` from local implementation evidence.

## Authoritative specification

## Description

将战略、产品、客户、流程、指标、政策和人员知识形成可供Human和Agent共同使用的语义层。

## Knowledge Domains

```text
Strategy
Objectives
Metrics
Products
Customers
Contracts
Processes
Roles
Policies
Risks
Decisions
Projects
Finance
Knowledge Articles
```

## Knowledge Node

```yaml
knowledge_node:
  node_id: string
  type: policy
  version: integer
  owner: string
  status: approved
  evidence: []
```

## Hard Rules

* Agent不能从非批准草稿推导正式政策；
* 知识状态需区分事实、假设和建议；
* 访问遵守数据边界；
* 冲突知识需显式；
* 重要知识有Owner；
* 知识更新触发依赖检查；
* 公司知识不能全部依赖向量检索。

## Acceptance Criteria

* 关键公司知识机器可读；
* Human和Agent使用同一事实；
* 版本和权限正确；
* 冲突知识可发现；
* 决策可引用知识来源；
* Agent幻觉因事实缺失而减少。

---

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
