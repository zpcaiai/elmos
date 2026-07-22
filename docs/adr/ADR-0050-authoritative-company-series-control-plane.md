# ADR-0050: Additive authoritative company-series control plane

## Status

Accepted on 2026-07-22.

## Context

The supplied company-series Batch 15–18 specifications define Skills 461–745, while existing repository files named Batch 15–18 already describe a separate technical-engine sequence. Reusing those paths or public table names would destroy valid prior work and create ambiguous evidence.

## Decision

Keep the technical-engine assets unchanged. Add distinct Skill groups, contracts and verification names for COGS, Agent Workforce, Vertical Solutions and Group Integration. Share one Java evidence protocol in `modules/company-series`, but preserve each model's exact sequential gates, dimensions, reports and final status. Store canonical logical database names inside dedicated PostgreSQL schemas using V24–V27.

The control plane may observe external authority evidence and write local projections. It cannot execute HR, finance, legal, board, Agent tool, regulatory, production migration, TSA, retirement or synergy-recognition actions. Every local output records `external_operation_executed=false`, and absent field evidence remains `NOT_RUN` or blocked.

## Consequences

- The two numbering sequences remain distinguishable without losing either implementation.
- Four batches share fail-closed mechanics while keeping authoritative models and gate labels intact.
- Dedicated schemas avoid collisions and permit exact logical table names.
- Local tests can prove software behavior but cannot self-certify real company, industry, Agent or transaction outcomes.
