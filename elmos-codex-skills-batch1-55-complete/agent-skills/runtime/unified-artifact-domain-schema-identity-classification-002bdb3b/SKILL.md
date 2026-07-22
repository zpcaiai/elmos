---
name: unified-artifact-domain-schema-identity-classification-002bdb3b
description: "分离不可变 Content Object、版本化 Artifact Metadata、分类、关系、授权和生命周期。"
---

# ART37A002 — 统一 Artifact Domain、Schema、Identity、Classification 与 Lifecycle

## Objective

分离不可变 Content Object、版本化 Artifact Metadata、分类、关系、授权和生命周期。

## Batch context

**Batch:** 37A — Artifact、Provenance 与 Evidence Fabric  
**Theme:** 统一 Artifact Schema、内容寻址、签名、SBOM、SLSA、证据图、对象锁、Retention 与离线验收包  
**Dependencies:** Batch 34 Tenant/Identity, Batch 35 SCM/Workspace, Batch 36 Runner/Sandbox/Execution Operations

## Required domain changes

- artifact.content_objects
- artifact.content_object_locations
- artifact.artifacts
- artifact.artifact_versions
- artifact.artifact_relationships
- artifact.artifact_classifications

Extend existing aggregates whenever they already exist. Do not introduce a parallel Tenant, Project, Artifact, Policy, Audit, Identity, Finding, Test, Control, Metric, Alert or Case model.

## Implementation requirements

- 实现 ContentDigest、ContentObjectId、ArtifactId、ArtifactVersionId 值对象。
- 支持 SHA-256/SHA-512 Hash Agility，并将 SHA-1 限制为只读遗留兼容。
- 元数据纠正创建新 Artifact Version；关系必须带证据来源。
- 实现 Artifact/Content API、UI 与 Tenant-aware Authorization。

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

- filenameIsNotArtifactIdentity
- contentObjectCannotBeModified
- metadataCorrectionCreatesNewVersion
- crossTenantDigestMatchDoesNotGrantRead

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
