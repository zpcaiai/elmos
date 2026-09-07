# Multi-tenant task and FinOps Skills integration

This repository pins `elmos-multitenant-task-finops-skills@1.0.0` from
`skills/subskills/elmos-multitenant-task-finops-skills-v1.0.0.zip` at SHA-256 `aa08e08a83dbfcef06119a8973b81be1af1bfa9c32cef6c94f0210ef62628d7b`.
The importer treats the ZIP as untrusted data, validates all 121
internal checksums, and does not execute its installers, validators, tests, or
other bundled scripts. The archive contains no license, signature, SBOM, or
provenance attestation; its pinned digest proves byte identity only.

## Installed Skills

Start repository-wide adoption with `$elmos-multitenant-task-finops-orchestrator`,
then select the narrowest downstream Skill:

- `$elmos-multitenant-task-finops-orchestrator`
- `$elmos-tenant-identity-rls`
- `$elmos-account-concurrency-admission`
- `$elmos-workload-aware-scheduler`
- `$elmos-task-lifecycle-temporal`
- `$elmos-task-progress-journal`
- `$elmos-checkpoint-recovery`
- `$elmos-task-io-artifact-archive`
- `$elmos-usage-metering-cost-ledger`
- `$elmos-revenue-margin-ledger`
- `$elmos-task-financial-analytics`
- `$elmos-concurrency-recovery-finops-certification`

The immutable source is retained under `skills/elmos-multitenant-task-finops-skills-v1.0.0`.
Codex-compatible, provenance-bound interfaces are installed under both
`.agents/skills` and `agent-skills/runtime`.

## Evidence and adoption boundary

The package's account-wide limit of exactly three active root tasks and durable
`WAITING_FOR_SLOT` behavior are source contracts. Installation does not prove
that the current application implements them. All 144 repository-specific
tasks remain `NOT_RUN`, external dependencies remain
`DECLARED_UNRESOLVED`, and certification remains `NOT_CERTIFIED`.

The packaged OpenAPI, AsyncAPI, schemas, configuration, and V100-V102 SQL are
reference material with status `NOT_APPLIED`. In particular,
the SQL is not copied into the repository's Flyway migrations because its UUID
and schema assumptions must first be reconciled with the canonical application
model. Real PostgreSQL, Temporal, provider, workload, tenant-isolation, recovery,
financial reconciliation, and production evidence remain `NOT_RUN`.
The repository-owned source risk register keeps eleven cross-contract findings open
and blocks direct adoption until their typed invariants are reconciled.

## Validation

Run `make multitenant-task-finops-skills`. Only repository-owned validation code
is executed.
