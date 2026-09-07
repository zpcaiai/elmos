# Implementation Guide — SQL Dual Execution Oracle

## Purpose

Run source and target SQL against real engines with equivalent fixtures and compare results, errors, state, trigger effects and transaction outcomes.

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

1. Provision exact real database engines
2. Execute source/target under controlled fixtures
3. Compare typed result sets and errors
4. Compare post-state, triggers and audit effects
5. Minimize data-dependent counterexamples

## Native acceptance corpus

- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-01` — result-set equivalence
- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-02` — NULL/decimal/time edge corpus
- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-03` — exception/error equivalence
- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-04` — trigger side effects
- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-05` — transaction rollback state
- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-06` — concurrent query scenario
- `ELMOS_SQL_DUAL_EXECUTION_ORACLE-07` — real-engine not H2

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
