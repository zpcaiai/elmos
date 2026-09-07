# Implementation Guide — Polyglot Route Certifier

## Purpose

Issue bounded route certificates only after exact frontend, backend, framework bridge, native build, differential, security, recovery, upgrade and rollback evidence closes required obligations.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Bind certificate to exact route envelope and RevisionSet
2. Require independent native and differential evidence
3. Record bounded semantics and allowed deltas
4. Set expiry and drift triggers
5. Refuse matrix-wide claims from a single route

## Native acceptance corpus

- `ELMOS_POLYGLOT_ROUTE_CERTIFIER-01` — certificate exact-version binding
- `ELMOS_POLYGLOT_ROUTE_CERTIFIER-02` — critical gap blocks
- `ELMOS_POLYGLOT_ROUTE_CERTIFIER-03` — three-repeat Golden Route
- `ELMOS_POLYGLOT_ROUTE_CERTIFIER-04` — holdout scenario
- `ELMOS_POLYGLOT_ROUTE_CERTIFIER-05` — upgrade and rollback evidence
- `ELMOS_POLYGLOT_ROUTE_CERTIFIER-06` — certificate expiry/revocation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
