# Implementation Guide — Authoritative Oracle Registry

## Purpose

Register compiler, protocol, database, contract, property, runtime and human authorities with independence, scope, confidence, freshness and conflict rules.

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

1. Classify authoritative versus advisory oracles
2. Bind oracle to subject, claim and version
3. Enforce producer/verifier separation
4. Resolve conflicting oracles without majority guessing
5. Expire stale or revoked oracle evidence

## Native acceptance corpus

- `ELMOS_AUTHORITATIVE_ORACLE_REGISTRY-01` — compiler oracle
- `ELMOS_AUTHORITATIVE_ORACLE_REGISTRY-02` — real database oracle
- `ELMOS_AUTHORITATIVE_ORACLE_REGISTRY-03` — protocol conformance oracle
- `ELMOS_AUTHORITATIVE_ORACLE_REGISTRY-04` — property oracle
- `ELMOS_AUTHORITATIVE_ORACLE_REGISTRY-05` — human authority
- `ELMOS_AUTHORITATIVE_ORACLE_REGISTRY-06` — conflicting oracle block

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
