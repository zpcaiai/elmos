# Release Gates

## P05 Deployment Complete

P05 proves deployment readiness rather than program semantics. It requires:

- exact application and verifier image digests;
- PostgreSQL migration status;
- `/livez`, `/readyz`, `/metrics`, `/version`;
- network policy and secretless solver sandbox;
- SBOM, vulnerability scan, signature and provenance;
- backup/restore and rollback rehearsal;
- evidence-store integrity and retention;
- authoritative release manifest.

## E1–E5

| Gate | Required evidence |
|---|---|
| E1 Static | inventory, parse coverage, source maps, schemas, architecture/security static checks |
| E2 Model | formal specs, assumptions, proof obligations, invariants, semantic profiles, model results |
| E3 Differential | translation validation, source/target traces, real database/runtime comparisons |
| E4 Failure injection | crash, timeout, partition, duplicate/reorder, stale owner, credit and recovery tests |
| E5 Customer Golden Route | repeatable commercial result on representative real repositories |

## Default P0 policy

A required P0 obligation passes only with current, non-stale evidence at or above its required assurance. Refuted, unknown, unsupported and assumption-required statuses deny. A bounded result passes only when the obligation explicitly requires at most A1 and `allowBounded=true`.

## Waivers

Waivers require two distinct approvers, an owner, reason, compensating controls, scope and expiry. Critical P0 authorization/noninterference properties cannot be waived under the default policy. Waiver approval changes the gate decision, never the technical result.

## Separation of duties

The author of a proof model cannot be the sole approver of a production waiver. Release evaluators and evidence storage identities are auditable.
