---
name: data-platform-provider-adapters-versioning-compatibilit-fb207916
description: "Implement Batch 44A Enterprise Data Platform、Lakehouse与Data Products provider adapters, capability discovery, API and schema versions, compatibility, migration and deprecation, covering Data Source、Dataset、Table、Stream、Data Product、Pipeline、Contract、Storage、Compute与Serving."
---

# Data Platform Provider Adapters Versioning Compatibility And Migration

## Objective

Implement Batch 44A Enterprise Data Platform、Lakehouse与Data Products provider adapters, capability discovery, API and schema versions, compatibility, migration and deprecation, covering Data Source、Dataset、Table、Stream、Data Product、Pipeline、Contract、Storage、Compute与Serving.

This Skill is part of the generated Batch 40–55 planning edition and requires domain-owner refinement before production implementation.

Extend approved ELMOS aggregates and services. Do not create parallel Tenant, Identity, Organization, Artifact, Policy, Audit, Case, Workflow, Contract, Finance, Customer or Data aggregates when an authoritative aggregate already exists.

## Scope

Implement the domain model, lifecycle, APIs, events, workflows, policy controls, provider adapters, evidence, analytics, operations and release gates required for **Batch 44A: Enterprise Data Platform、Lakehouse与Data Products**.

Theme:

```text
Data Source、Dataset、Table、Stream、Data Product、Pipeline、Contract、Storage、Compute与Serving
```

Core objects:

- Data Source
- Dataset
- Data Product
- Pipeline
- Table
- Stream
- Storage
- Serving Endpoint

## Preconditions

1. Read the repository-level `AGENTS.md`, architecture decisions and earlier Batch packages.
2. Inventory existing domain objects, providers, schemas, events, policies, workflows, reports and operational ownership.
3. Identify the authoritative source for every object and decision used by this capability.
4. Resolve Tenant, Legal Entity or Organization scope, actor/workload identity, purpose, effective period and classification.
5. Write unresolved domain assumptions to `docs/implementation/data-platform-provider-adapters-versioning-compatibility-and-migration-baseline.md`.

## Required Capabilities

- Implement Data Source、Dataset、Table、Stream、Data Product、Pipeline、Contract、Storage、Compute与Serving without weakening earlier identity, evidence, policy, finance, privacy or tenant-isolation controls.
- Model lifecycle and state transitions explicitly, including partial, unknown, rejected, superseded and recovery states.
- Preserve immutable source observations and versioned interpretations, plans, decisions, configurations and projections.
- Provide typed APIs, commands, events and adapter contracts; keep provider DTOs outside the core domain.
- Support idempotency, optimistic concurrency, effective dating, backfill, tombstones, reconciliation and replay.
- Add field-level authorization, source locality, purpose limitation, retention and export controls where data is sensitive.
- Add operational ownership, SLAs, alerts, cases, remediation, reverification and immutable completion evidence.
- Add analytical definitions with grain, numerator, denominator, source lineage, as-of time and confidence where metrics are involved.

## Core Workflow

```text
ingest→validate→transform→publish→serve→observe→evolve→retire
```

Each transition must record subject, prior version, new version, actor/workload, policy version, reason, timestamp, correlation ID and evidence references.

## Required Artifacts

```text
data_platform_provider_adapters_versioning_compatibility_and_migration_manifest.json
data_platform_provider_adapters_versioning_compatibility_and_migration_state.json
data_platform_provider_adapters_versioning_compatibility_and_migration_decision.json
data_platform_provider_adapters_versioning_compatibility_and_migration_reconciliation.json
data_platform_provider_adapters_versioning_compatibility_and_migration_evidence.json
```

Artifacts must identify Tenant, subject, version, source snapshot, policy or model versions, effective period, result status, limitations, integrity digest and evidence references.

## Security, Governance and Domain Invariants

- 原始数据不可静默覆盖
- Data Product有Owner和Contract
- Schema演进版本化
- Pipeline重试幂等
- 计算层不成为唯一事实源
- `UNKNOWN`, `INCONCLUSIVE`, `PARTIAL`, timeout and unreconciled external state never imply success.
- Active definitions and published snapshots are immutable; corrections create new versions or compensating records.
- Cross-tenant and cross-organization access is enforced at API, service, database, cache, event, search, analytics and export boundaries.
- Automation and AI recommendations cannot approve regulated, financial, safety, employment, security or contractual decisions unless an explicit governed policy allows a typed low-risk action.
- Sensitive data and secrets are redacted before logs, analytics, exports or evidence persistence.

## Workflow

1. Discover the current implementation and authoritative records.
2. Capture a bounded immutable input snapshot.
3. Validate identity, scope, schema, policy, effective period and preconditions.
4. Execute deterministic logic or a versioned approved provider adapter.
5. Persist state and outbox atomically for material transitions.
6. Reconcile asynchronous, external, distributed or inferred results before advancing.
7. Produce source-linked evidence and operational telemetry.
8. Run negative, lifecycle, idempotency, privacy, tenant-isolation, recovery and release-gate tests.

## Implementation Requirements

- Add schema migrations with tenant-aware foreign keys, RLS where applicable, uniqueness and lifecycle constraints.
- Add domain services, ports/adapters and normalized event contracts.
- Add idempotency keys, source/version fields, status histories, tombstones and reconciliation states.
- Add audit records, outbox events, metrics, traces, alerts, runbooks and operator actions.
- Add source-to-result lineage and evidence references.
- Add capability and version discovery for provider- or standard-sensitive integrations.
- Add migration, backfill and replay tools that preserve history.

## Required Tests

```text
dataSourceIdentityIsStable
dataSourceLifecycleIsVersioned
datasetIdentityIsStable
datasetLifecycleIsVersioned
dataProductIdentityIsStable
dataProductLifecycleIsVersioned
pipelineIdentityIsStable
pipelineLifecycleIsVersioned
providerAdaptersVersioningCompatibilityAndMigrationPreservesSourceLineage
duplicateRequestIsIdempotent
unknownStateDoesNotImplySuccess
staleOrSupersededVersionIsRejected
crossTenantAccessIsRejected
unauthorizedOverrideIsRejected
```

Also add domain unit tests, migration tests, provider-contract tests, property tests, authorization tests, privacy tests, reconciliation tests, chaos tests and scale tests.

## Verification

Run the repository-native builds and tests plus:

```bash
./validate.sh
```

Record exact commands, versions, outputs, skipped tests and reasons. Static Skill-package validation does not certify a production implementation, provider integration, regulatory conclusion or domain outcome.

## Stop and Escalate

Stop and report `BLOCKED` when:

- the authoritative subject, owner, source, scope, effective period or stable identity cannot be established;
- required tenant isolation, authorization, approval, segregation, consent, safety or legal controls cannot be enforced;
- implementation requires destructive history rewrites, fail-open behavior, arbitrary privileged code or plaintext secrets;
- an external side effect cannot be made idempotent or reconciled;
- a mandatory domain, provider, policy, evidence, retention, integrity or release requirement is unavailable;
- passing requires weakening an earlier ELMOS invariant.

## Definition of Done

- Domain objects and lifecycle states are implemented and versioned.
- Authoritative source lineage and effective dating are complete.
- Tenant, organization and resource authorization are enforced end to end.
- Idempotency, concurrency, unknown-state reconciliation, correction and recovery are tested.
- Provider capabilities and limitations are explicit.
- Evidence is complete, immutable, integrity-protected and redacted.
- APIs, events, migrations, observability, operations and runbooks are present.
- Negative, security, privacy, resilience and release-gate tests pass.

## Completion Report

Return:

1. architecture and reused aggregates;
2. domain tables, state machines and effective-date semantics;
3. APIs, events, workflows and provider adapters;
4. security, privacy, approval and policy controls;
5. reconciliation, evidence, observability and recovery;
6. exact tests and results;
7. files and migrations;
8. unresolved domain, provider, regulatory or product limitations.
