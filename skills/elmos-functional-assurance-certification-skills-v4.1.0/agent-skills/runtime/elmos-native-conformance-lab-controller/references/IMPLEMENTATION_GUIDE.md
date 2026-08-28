# Implementation Guide — Native Conformance Lab Controller

## Purpose

Operate independent exact-version labs for frameworks, protocols, languages, databases and cloud runtimes with repeatable fixtures and authoritative native commands.

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

1. Provision exact native runtimes and dependencies
2. Attest lab configuration and runner identity
3. Run minimal, representative, negative, upgrade and recovery fixtures
4. Keep lab isolated from generator control
5. Retain replayable command/evidence bundle

## Native acceptance corpus

- `ELMOS_NATIVE_CONFORMANCE_LAB_CONTROLLER-01` — framework native import/start
- `ELMOS_NATIVE_CONFORMANCE_LAB_CONTROLLER-02` — protocol interoperability
- `ELMOS_NATIVE_CONFORMANCE_LAB_CONTROLLER-03` — real database execution
- `ELMOS_NATIVE_CONFORMANCE_LAB_CONTROLLER-04` — cloud runtime smoke
- `ELMOS_NATIVE_CONFORMANCE_LAB_CONTROLLER-05` — upgrade/rollback fixture
- `ELMOS_NATIVE_CONFORMANCE_LAB_CONTROLLER-06` — lab rebuild reproducibility

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
