---
name: artifact-fabric-replication-backup-scrubbing-migration-52e41d83
description: "实现多副本、分层存储、完整性巡检、Provider 迁移、恢复、索引/图重建与DR演练。"
---

# ART37A015 — Artifact Fabric Replication、Backup、Scrubbing、Migration 与 DR

## Objective

实现多副本、分层存储、完整性巡检、Provider 迁移、恢复、索引/图重建与DR演练。

## Batch context

**Batch:** 37A — Artifact、Provenance 与 Evidence Fabric  
**Theme:** 统一 Artifact Schema、内容寻址、签名、SBOM、SLSA、证据图、对象锁、Retention 与离线验收包  
**Dependencies:** Batch 34 Tenant/Identity, Batch 35 SCM/Workspace, Batch 36 Runner/Sandbox/Execution Operations

## Required domain changes

- operations.artifact_replication_profiles
- operations.artifact_replication_jobs
- operations.artifact_scrubbing_runs
- operations.artifact_migration_plans
- operations.artifact_restore_runs
- operations.artifact_dr_drills

Extend existing aggregates whenever they already exist. Do not introduce a parallel Tenant, Project, Artifact, Policy, Audit, Identity, Finding, Test, Control, Metric, Alert or Case model.

## Implementation requirements

- 复制后重新验证目标 Digest、Encryption、Retention 与 Lock。
- 巡检检测 Metadata/Object 缺失、错误摘要、错误分类和错误加密键。
- 迁移采用 Copy→Verify→Dual-read→Switch→Observe→Retire。
- 恢复后验证 Legal Hold、Trust Root、Relationships，并重建 Graph/Search Index。

All state-changing operations must use idempotency, tenant-aware authorization, audit records, and transaction-plus-outbox or an equivalent reconciliation-safe pattern.

## Security and correctness invariants

- Content Object 与 Artifact Metadata、Attestation、Verification Decision、Evidence Pack 必须分离。
- Content Object 不可变；内容或元数据纠正必须创建新版本或新对象。
- Artifact、Attestation 与关系必须通过带算法的内容摘要绑定，不得只依赖文件名、标签、路径或对象键。
- 签名有效不等于业务验证通过；Producer Claim 与 Verifier Decision 必须是不同角色和记录。
- 跨租户内容去重默认关闭；相同 Digest 不授予读取权限。
- 离线验收包必须携带完成离线验证所需的 Trust Root、Policy、Timestamp/Transparency Evidence 和工具摘要。
- Retention、Object Lock 与 Legal Hold 作用于精确对象版本，且到期后仍需 Disposition Workflow。
- 图数据库仅作为可重建 Projection，PostgreSQL 与不可变 Artifact 是事实来源。

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

- replicaDigestIsVerified
- metadataWithoutObjectIsDetected
- migrationUsesDualReadBeforeSwitch
- restorePreservesLegalHold

Also include:

- cross-tenant isolation tests;
- stale-version and replay tests;
- authorization and secret-exclusion tests;
- idempotency and concurrent-update tests;
- failure, timeout and unknown-result reconciliation tests;
- migration and backward-compatibility tests.

## Hard stop conditions

Stop implementation and report `BLOCKED` when any of the following is true:

- Artifact 身份仍依赖可变文件名、对象键或标签。
- 历史 Evidence 可被原地覆盖。
- 私钥需要写入数据库、日志或 Evidence Pack。
- Subject 无法绑定 Content Digest。
- Source Locality、Tenant Authorization 或 Legal Hold 无法执行。

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
