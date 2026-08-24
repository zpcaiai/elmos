---
name: elmos-task-io-artifact-archive
id: ELMOS-MTF-008
version: 1.0.0
description: Archive every task input, execution manifest, output, artifact, log segment, and versioned evidence with object-storage references and database metadata.
layer: storage
risk: high
depends_on:
  - elmos-task-progress-journal
  - elmos-checkpoint-recovery
---

# elmos-task-io-artifact-archive

## Purpose

Make task history statistically useful and auditable without placing large binary or log payloads directly in PostgreSQL.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- Small structured parameters are stored as validated JSONB; large files, logs, repositories, generated code, PDFs, images, and archives reside in S3-compatible object storage.
- Every object has tenant, task, run, content type, size, SHA-256 digest, encryption/key reference, retention class, and immutable version.
- The original encrypted input may be retained according to policy; searchable/display copies are redacted.
- Outputs are append-only versions and are never overwritten in place.
- Database records contain no live provider secrets or reusable repository credentials.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Create immutable input manifests for text, multimodal files, repository snapshots, settings, and user instructions.
- Store content-addressed objects and link them to task, run, node, and artifact roles.
- Record execution environment, dependency lock, model/tool versions, policy version, and cache lineage.
- Produce output artifact manifests with checksums and evidence bindings.
- Apply retention, legal hold, tenant export, and cryptographic deletion policies.
- Verify object integrity during recovery and before result delivery.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-008-T01` | Define input and output manifest schemas. | required |
| `ELMOS-MTF-008-T02` | Store small validated task parameters in JSONB. | required |
| `ELMOS-MTF-008-T03` | Store large payloads in tenant-scoped object storage. | required |
| `ELMOS-MTF-008-T04` | Compute and verify SHA-256 content digests. | required |
| `ELMOS-MTF-008-T05` | Record execution environment and version lineage. | required |
| `ELMOS-MTF-008-T06` | Version outputs and artifacts append-only. | required |
| `ELMOS-MTF-008-T07` | Segment and archive logs outside PostgreSQL. | required |
| `ELMOS-MTF-008-T08` | Implement redacted searchable projections. | required |
| `ELMOS-MTF-008-T09` | Implement retention classes and legal hold. | required |
| `ELMOS-MTF-008-T10` | Implement tenant export and deletion. | required |
| `ELMOS-MTF-008-T11` | Prevent secret and credential persistence. | required |
| `ELMOS-MTF-008-T12` | Run integrity, retention, and cross-tenant object-access tests. | required |

## Primary outputs

- `input-manifest.schema.json`
- `artifact-manifest.schema.json`
- `object-key-policy.md`
- `retention-policy.yaml`
- `export-delete-workflows.md`
- `integrity-verification-report.json`

## Acceptance criteria

- Every delivered result can be traced to its exact input manifest, run, nodes, tool/model versions, and artifact digest.
- Large outputs do not bloat transactional tables.
- A missing or modified object is detected before recovery or delivery.
- Tenant deletion removes or cryptographically renders inaccessible all eligible task objects.

## Required tests

- Unit tests for state transitions, formulas, policy decisions, and idempotency.
- PostgreSQL integration tests with a non-superuser role and real RLS.
- Temporal integration and workflow replay tests when workflow behavior is in scope.
- Multi-replica concurrency tests for race-sensitive behavior.
- Failure-injection and recovery tests for long-running or side-effecting behavior.
- Contract tests for APIs, events, schemas, and object manifests.
- Financial reconciliation tests whenever usage, cost, revenue, or margin is in scope.

## Evidence contract

For every completed task, record:

- repository commit SHA and migration version;
- environment, tenant/account fixtures, and configuration digest;
- executed command and machine wall-clock duration;
- test result, trace IDs, task/run IDs, and relevant event sequences;
- database/object-store evidence references;
- assumptions, residual risks, waivers, owner, and expiry.

## Production-claim boundary

This Skill is an implementation specification. Do **not** claim the Elmos target repository has implemented or passed this capability until repository-specific migrations, code, tests, load runs, recovery campaigns, tenant-isolation checks, provider reconciliation, and release gates have produced executable evidence.
