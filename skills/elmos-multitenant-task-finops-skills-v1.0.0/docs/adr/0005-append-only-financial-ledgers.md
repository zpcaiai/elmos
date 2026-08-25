# ADR-0005 — Append-only usage and revenue ledgers

## Status
Accepted.

## Context
Mutable cost/revenue totals are not auditable and cannot reliably handle duplicate provider records, price changes, refunds, FX, or corrections.

## Decision
Store immutable signed usage and revenue entries. Snapshot price/FX on usage. Apply corrections/refunds as new entries. Keep summaries as rebuildable projections.

## Consequences
- Totals are reproducible and drillable.
- Idempotency/provider receipt keys are mandatory.
- Reconciliation workflows and data-quality states are required.
