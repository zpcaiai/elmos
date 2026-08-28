---
name: storage-search-cache-validation
description: Validate all declared Durable Storage, Object Artifacts, Search and Cache capabilities with executable positive, boundary, adversarial, concurrency, recovery and evidence-backed release tests.
---

# Durable Storage, Object Artifacts, Search and Cache Validation

## Purpose

Use this Skill to plan, execute and certify the `storage-search-cache` product domain. It owns **63 declared capabilities** (36 P0, 22 P1, 5 P2) across 4 execution contexts and four mandatory variants.

## Inputs

- Frozen release candidate and feature-registry revision.
- Tenant, project, environment authority, budget and fencing context.
- Concrete cases from `suites/full-product.jsonl` whose business line is `storage-search-cache`.
- Exact provider, browser, SDK, database or infrastructure profiles required by each case.
- Hidden-test authority and sealed evidence destination.

## Workflow

1. Resolve every feature ID to `matrices/feature-registry.yaml` and reject unknown or untested functionality.
2. Provision an isolated context for: postgresql, object-storage, search-index, redis-cache.
3. Execute nominal, boundary, negative-security and concurrent-recovery variants.
4. Capture API/UI/event/state traces before normalization.
5. Apply the domain Oracle `storage-durability-consistency-isolation-integrity-and-recovery` plus security, state, audit and unsupported-disclosure Oracles.
6. Reconcile side effects, retry receipts, checkpoints, usage and tenant ownership.
7. Seal evidence and return pass, fail, blocked or unavailable; never infer success from compilation or HTTP status alone.

## Capability surface

Representative capabilities include: Postgresql Is Source Of Truth, Schema Migration Forward, Schema Migration Rollback Or Compensation, Row Level Security, Tenant Partition Key, Transaction Isolation And Locking, Idempotency Unique Constraint, Outbox Same Transaction, Database Failover, Connection Pool Exhaustion, Backup And Restore, Point In Time Recovery. The complete source of truth is `matrices/full-product.yaml`; no prose list may override it.

## Mandatory negative and recovery coverage

- Unauthorized, cross-tenant, replayed, stale, malformed and over-budget requests.
- Duplicate delivery, partial commit, provider timeout, worker loss and resume from durable checkpoint.
- Secret exposure, prompt/tool injection and unsafe output where AI or external content is involved.
- Concurrency races, idempotency conflicts and stale fencing-token rejection.
- Failure disclosure: unsupported or unavailable paths must block a success claim.

## Release gates

- Feature binding coverage: 100%.
- P0 critical Oracle pass: 100%; P0 SSER: 0.
- Unavailable Adapter or environment profile: 0 for release.
- Cross-tenant leakage, privilege expansion, duplicate charge or unreconciled side effect: 0.
- Evidence completeness and provenance integrity: 100%.

## Production Adapter

Route execution through `external-storage-search-cache-harness` under `integrations/harness/full-product-adapters.yaml`. An adapter stub or skipped case is implementation progress, not product certification.

## Outputs

- Per-case result and normalized Oracle findings.
- Raw trace, state, security and recovery evidence.
- Feature coverage deltas, failure clusters and permanent regressions.
- Signed domain certificate or a fail-closed blocker report.
