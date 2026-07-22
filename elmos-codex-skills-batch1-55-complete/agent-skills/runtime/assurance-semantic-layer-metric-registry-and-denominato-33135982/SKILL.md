---
name: assurance-semantic-layer-metric-registry-and-denominato-33135982
description: "建立统一Metric定义、Grain、分子分母、适用性、时间、聚合、目标、护栏、Snapshot与Restatement。"
---

# ANA37C002 — Assurance Semantic Layer、Metric Registry 与 Denominator Governance

## Objective

建立统一Metric定义、Grain、分子分母、适用性、时间、聚合、目标、护栏、Snapshot与Restatement。

## Batch context

**Batch:** 37C — Evidence Analytics 与 Assurance Cockpit  
**Theme:** 证据完整度、供应链风险、审计就绪度、趋势、异常、到期预警、控制覆盖、Portfolio Assurance 与高管/审计驾驶舱  
**Dependencies:** Batch 37A Evidence Fabric, Batch 37B External Producers, Batch 38 Policy/Control candidates

## Required domain changes

- analytics.semantic_models
- analytics.metric_definitions
- analytics.metric_denominators
- analytics.metric_applicability_rules
- analytics.metric_snapshots
- analytics.metric_restatements

Extend existing aggregates whenever they already exist. Do not introduce a parallel Tenant, Project, Artifact, Policy, Audit, Identity, Finding, Test, Control, Metric, Alert or Case model.

## Implementation requirements

- Metric角色支持Outcome/Driver/Guardrail/Diagnostic/Detail。
- Ratio必须定义Applicable Denominator；Missing Behavior与Aggregation Rule必填。
- Snapshot保存As-of、Latest Complete Data、Numerator、Denominator、Value、Quality、Source IDs与Calculation Hash。
- Late Evidence/Backfill/Applicability变更创建Restatement而不覆盖历史。

All state-changing operations must use idempotency, tenant-aware authorization, audit records, and transaction-plus-outbox or an equivalent reconciliation-safe pattern.

## Security and correctness invariants

- 每个 Metric 必须定义业务含义、Grain、Numerator、Denominator、Applicable Population、时间窗口和数据质量要求。
- Missing、Unknown、Not Applicable、Fail 与 Zero 必须严格区分。
- Evidence Presence、Evidence Verification 与 Control Operating Effectiveness 是不同概念。
- Portfolio Ratio 必须重新汇总 Numerator/Denominator，不得直接平均项目百分比。
- Critical Project、Critical Control 与 Unknown Coverage 不能被总分或平均值隐藏。
- Dashboard 仅使用注册 Semantic Metric，必须显示 As-of、Latest Complete Data、Metric Version 与数据质量。
- Anomaly、Forecast 和 Narrative 必须保存方法、基线、假设、置信度与源 Snapshot，不能虚构因果。
- Auditor Access、Sampling、Export 与 Drill-down 必须可重现、只读、按范围授权并保持 Tenant 隔离。

## Required implementation workflow

1. Inventory existing code, schemas, APIs, jobs, providers, policies, indexes and UI related to this skill.
2. Record baseline behavior, gaps, conflicting models and migration risks under the relevant `docs/` path.
3. Extend the existing domain model and add forward-only database migrations.
4. Implement provider-neutral interfaces before provider adapters.
5. Add application services, APIs, authorization and audit.
6. Add operator and reviewer UI where the workflow requires human action.
7. Add metrics, traces, alerts and machine-readable evidence.
8. Add unit, integration, tenant-isolation, negative and recovery tests.
9. Run the repository validation commands and record exact results.

## Required tests

- ratioRequiresDenominator
- metricRequiresGrain
- portfolioRatioAggregatesNumeratorAndDenominator
- restatementDoesNotOverwriteOldSnapshot

Also include:

- cross-tenant isolation tests;
- stale-version and replay tests;
- authorization and secret-exclusion tests;
- idempotency and concurrent-update tests;
- failure, timeout and unknown-result reconciliation tests;
- migration and backward-compatibility tests.

## Hard stop conditions

Stop implementation and report `BLOCKED` when any of the following is true:

- Metric Grain 或 Denominator 无法定义。
- 数据源 Grain、Freshness 或 Tenant Scope 不明确。
- Portfolio 汇总会隐藏 Critical Failure。
- Dashboard 需要跨 Tenant 直接访问原始表。
- Alert、Narrative 或 Audit Export 无法链接源 Evidence。

## Deliverables

- domain entities, value objects and state transitions;
- database migrations, indexes, constraints and RLS updates;
- service interfaces and provider adapters;
- APIs and request/response schemas;
- user, reviewer or operator UI where applicable;
- audit events, outbox events, metrics and traces;
- fixtures, test data and conformance tests;
- machine-readable release evidence;
- documentation of provider, standard, legal or analytical limitations.

## Done criteria

This skill is complete only when:

- the objective is implemented through the approved ELMOS aggregates;
- immutable facts and historical versions remain reproducible;
- Tenant, authorization, classification and retention boundaries are enforced;
- all listed tests and Batch-level release gates pass;
- unknown, partial, inconclusive and failed states are not converted to success;
- exact commands, results, migrations and unresolved limitations are reported.

## Completion report

Return:

1. architecture and domain changes;
2. schema migrations and indexes;
3. APIs, providers and UI;
4. security and tenant boundaries;
5. state machines and idempotency behavior;
6. exact test commands and results;
7. release-evidence paths;
8. unsupported capabilities and follow-up work.
