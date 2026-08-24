---
name: elmos-tenant-identity-rls
id: ELMOS-MTF-002
version: 1.0.0
description: Enforce tenant and account identity, PostgreSQL RLS, least privilege, auditability, and cross-tenant isolation for all task and financial data.
layer: security
risk: critical
depends_on:
  - elmos-multitenant-task-finops-orchestrator
---

# elmos-tenant-identity-rls

## Purpose

Make tenant isolation non-bypassable and ensure the three-task limit is attached to the authenticated account rather than a spoofable request header.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- tenant_id and account_id are derived from verified OIDC identity and membership, never trusted from X-Tenant-Id or arbitrary client JSON.
- Every tenant business table has ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY.
- Application runtime roles are non-superuser, do not own protected tables, and do not have BYPASSRLS.
- The global account slot table is readable only by the owning account and controlled services; occupied task data remains tenant-scoped.
- Inputs, outputs, prompts, logs, and financial dimensions are encrypted and redacted according to data classification.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Implement OIDC/JWT validation and resolve tenant membership server-side.
- Set transaction-local app.tenant_id, app.account_id, app.actor_id, and app.request_id after authorization.
- Apply RLS policies to tasks, runs, nodes, events, checkpoints, artifacts, usage, revenue, and aggregates.
- Create separate migration-owner, application, workflow, analytics, and break-glass roles.
- Add cross-tenant attack tests using a non-superuser runtime role.
- Audit membership changes, quota changes, task control actions, cost overrides, price-book changes, refunds, and retention actions.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-002-T01` | Define OIDC claims and membership resolution rules. | required |
| `ELMOS-MTF-002-T02` | Remove all trust in client-provided tenant headers. | required |
| `ELMOS-MTF-002-T03` | Define transaction-local identity context propagation. | required |
| `ELMOS-MTF-002-T04` | Create non-superuser database roles and grants. | required |
| `ELMOS-MTF-002-T05` | Enable and force RLS on all tenant-scoped task tables. | required |
| `ELMOS-MTF-002-T06` | Create account-owner policies for global concurrency slots. | required |
| `ELMOS-MTF-002-T07` | Add admin and workflow-service access through explicit least-privilege paths. | required |
| `ELMOS-MTF-002-T08` | Classify task inputs, outputs, logs, prompts, usage, and revenue fields. | required |
| `ELMOS-MTF-002-T09` | Implement encryption-key references and log redaction. | required |
| `ELMOS-MTF-002-T10` | Audit all privileged task and finance operations. | required |
| `ELMOS-MTF-002-T11` | Add tenant export, retention, and deletion workflows. | required |
| `ELMOS-MTF-002-T12` | Execute cross-tenant, confused-deputy, and BYPASSRLS tests. | required |

## Primary outputs

- `identity-context-contract.md`
- `rls-migration.sql`
- `role-matrix.csv`
- `data-classification.yaml`
- `tenant-isolation-test-report.json`
- `audit-policy.md`

## Acceptance criteria

- A forged tenant header cannot read, write, start, cancel, resume, meter, or bill another tenant's task.
- A runtime database role cannot bypass RLS even when issuing raw SQL.
- One account's active slots cannot be claimed or released by another account.
- Audit records identify tenant, account, actor, request, task, run, and trace.

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
