---
name: b37-extension-configuration-state-data-migration
description: "Implement extension configuration schema state data and secret-reference migration with dry-run checkpoints reconciliation rollback and mixed-version compatibility."
---

# Skill B37-X07: b37-extension-configuration-state-data-migration

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Migration never copies secret values into configuration artifacts.
- Customer-owned data is not deleted or transformed without explicit policy and backup.
- An upgrade cannot activate before migration and reconciliation succeed.

## Workflow

1. Inventory configuration, secret references, extension-owned state, customer-owned data, schemas, versions, retention, and rollback constraints.
2. Define typed forward and backward migration steps with idempotency, checkpoints, backups, and validation.
3. Run dry-run and shadow migration, then canary upgrade under a mixed-version compatibility window.
4. Reconcile record counts, invariants, digests, permissions, and secret references before activation.
5. Exercise rollback or compensating migration and remove temporary compatibility only after old versions are drained.

## Required repository outputs

- `migrations/extension-migration.json`
- configuration schema migration, state migration, reconciliation, rollback, and mixed-version evidence

## Verification

- Run `validate_extension_migration.py`.
- Prove forward, retry, rollback, crash recovery, and mixed-version scenarios.

## Stop and escalate when

- No reversible or compensating strategy exists for P0 state.
- Data ownership, retention, or secret boundary is ambiguous.

## Definition of done

- Configuration and state upgrades are idempotent, reconciled, reversible, and safe across supported mixed versions.
