---
name: external-evidence-conformance-fixtures-security-chaos-a-de42adcf
description: "实现Connector TCK、平台Fixtures、真实平台Smoke、恶意报告、Webhook丢失、Schema Drift、Scale与发布门禁。"
---

# EVI37B016 — External Evidence Conformance、Fixtures、安全、Chaos 与 Release Gates

## Objective

实现Connector TCK、平台Fixtures、真实平台Smoke、恶意报告、Webhook丢失、Schema Drift、Scale与发布门禁。

## Batch context

**Batch:** 37B — Evidence Producer Integrations  
**Theme:** Jenkins、GitHub Actions、GitLab CI、Azure Pipelines、SonarQube、SCA/SAST、Test、Performance 与第三方审计证据接入  
**Dependencies:** Batch 37A Artifact and Evidence Fabric, Batch 35 SCM Connectors, Batch 34 Workload Identity

## Required domain changes

- operations.external_connector_tck_runs
- operations.external_fixture_runs
- operations.external_platform_smoke_runs
- operations.external_evidence_gate_runs

Extend existing aggregates whenever they already exist. Do not introduce a parallel Tenant, Project, Artifact, Policy, Audit, Identity, Finding, Test, Control, Metric, Alert or Case model.

## Implementation requirements

- 验证级别区分 Unit/Contract/Fixture/Real Cloud/Real Self-managed/Customer/Unverified。
- Fixtures覆盖缺测试、失败构建有效报告、重跑、Matrix、过期Artifact、恶意ZIP、Partial SARIF、Secret、不可比性能和撤回审计。
- 测试Credential Revocation、Rate Limit、Interrupted Download、Schema Drift与Connector Restart。
- 生成 build/evidence/external-evidence-producer-gate.json。

All state-changing operations must use idempotency, tenant-aware authorization, audit records, and transaction-plus-outbox or an equivalent reconciliation-safe pattern.

## Security and correctness invariants

- 外部平台提供的是原始声明和观察，不是 ELMOS 最终 Verification Decision。
- Native Evidence 与 Normalized Evidence 必须同时保存，转换损失必须生成 Loss Report。
- 每个运行、作业、构件和报告必须使用 Provider Instance + Native Stable ID 标识；名称只是别名。
- 下载对象必须由 ELMOS 独立计算 SHA-256；Provider Fingerprint/ETag 仅作辅助。
- Webhook 必须由 Polling、Backfill 与 Watermark Reconciliation 补充。
- 外部成功状态不得自动覆盖测试失败、安全发现、证据缺失或 ELMOS Policy。
- Secret Scanner 不得保存完整 Secret；测试重跑不得删除最初失败；性能比较必须先判断环境可比性。
- 第三方审计报告只作为 External Claim，必须验证签名、范围、期间、修订和撤回。

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

- connectorCannotCrossTenant
- webhookLostPollingRecovers
- maliciousArchiveTraversalIsRejected
- externalEvidenceReleaseGatePasses

Also include:

- cross-tenant isolation tests;
- stale-version and replay tests;
- authorization and secret-exclusion tests;
- idempotency and concurrent-update tests;
- failure, timeout and unknown-result reconciliation tests;
- migration and backward-compatibility tests.

## Hard stop conditions

Stop implementation and report `BLOCKED` when any of the following is true:

- Connector 无法绑定单一 Tenant 和明确 Provider Scope。
- Native Evidence 无法保存、摘要或版本化。
- 外部 Token 只能明文持久化。
- Build 无法关联 Repository 与精确 Commit。
- 外部绿色状态被直接映射为 ELMOS PASS。

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
