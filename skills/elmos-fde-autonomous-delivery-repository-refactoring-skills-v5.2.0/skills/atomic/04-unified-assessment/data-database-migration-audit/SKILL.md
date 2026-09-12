---
name: data-database-migration-audit
description: Audit schemas, queries, routines, ORM behavior, lineage, quality, retention, migrations, reconciliation, and database portability.
---

# Mission

Audit schemas, queries, routines, ORM behavior, lineage, quality, retention, migrations, reconciliation, and database portability.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- database audit
- schema review
- slow query
- migration risk
- SQL routine analysis

## Do not use when

- run destructive query on production
- infer data meaning from column names alone

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Inventory databases, schemas, access paths, data classes, and migration history.
2. Extract schema and routine semantics into DB-SIR.
3. Correlate application queries, ORM mappings, runtime plans, locks, and incidents.
4. Model migration, backfill, reconciliation, and rollback obligations.
5. Reproduce material issues on representative sanitized data.
6. Publish findings, migration risk, and data proof obligations.

## Required outputs

- database assessment
- schema and routine model
- query findings
- migration risk register
- reconciliation obligations

## Invariants

- no claim without evidence
- no authority escalation
- all unknowns are explicit
- outputs bind to exact RevisionSet

## Fail closed on

- insufficient evidence
- unsupported technology
- stale RevisionSet
- authority denied
- validation failure
- Material `UNKNOWN`, `UNSUPPORTED`, stale evidence, unresolved critical side effects, or missing approvals.
- Any attempt by this Skill or an Adapter to become the canonical completion authority.

## Authority and side effects

Default deny. Read, workspace-write, external-write, and production-write are separate capabilities. Production writes are prohibited by this capability package. Tool results must be intercepted and checked against the approved plan before commit. Checkpoint before external effects and after each accepted ChangeSet.

## Definition of done

- All checks in `acceptance.yaml` pass with exact revision and environment identity.
- Evidence, counterexamples, unknowns, decisions, cost, and machine wall-clock are recorded.
- An independent verifier returns the result to K8; the producer does not self-approve.
- The maximum standalone claim is E3 capability readiness. E4/E5/P05 require the independent companion package and authorized customer execution.

## Local dependencies

- `issue-ontology-and-finding-normalization`
- `data-event-permission-lineage`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
