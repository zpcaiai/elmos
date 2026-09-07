# Implementation Guide — Flake Quarantine Governor

## Purpose

Detect, classify, quarantine and remediate flaky tests without allowing retries or quarantine to make critical release gates falsely green.

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

1. Track first failure and every retry
2. Classify environment, order, timing and test defects
3. Require owner, expiry and remediation SLA
4. Keep critical quarantined tests blocking
5. Measure flake rate as release quality signal

## Native acceptance corpus

- `ELMOS_FLAKE_QUARANTINE_GOVERNOR-01` — intermittent timing test
- `ELMOS_FLAKE_QUARANTINE_GOVERNOR-02` — order-dependent test
- `ELMOS_FLAKE_QUARANTINE_GOVERNOR-03` — environment capacity flake
- `ELMOS_FLAKE_QUARANTINE_GOVERNOR-04` — retry-success remains flaky
- `ELMOS_FLAKE_QUARANTINE_GOVERNOR-05` — quarantine expiry
- `ELMOS_FLAKE_QUARANTINE_GOVERNOR-06` — critical flake blocks release

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
