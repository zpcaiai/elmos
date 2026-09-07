# Implementation Guide — Security Control Coverage and Defeater Analyzer

## Purpose

Map threats to preventive, detective, responsive and recovery controls, identify defeaters and prevent checkbox coverage claims.

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

1. build threat-control-evidence graph
2. check independence and failure correlation
3. identify assumptions and control bypasses
4. measure negative-test and monitoring coverage
5. propagate unresolved defeaters to certification

## Native acceptance corpus

- `ELMOS_SECURITY_CONTROL_COVERAGE_DEFEATER_ANALYZER-01` — native scenario: build threat-control-evidence graph
- `ELMOS_SECURITY_CONTROL_COVERAGE_DEFEATER_ANALYZER-02` — native scenario: check independence and failure correlation
- `ELMOS_SECURITY_CONTROL_COVERAGE_DEFEATER_ANALYZER-03` — native scenario: identify assumptions and control bypasses
- `ELMOS_SECURITY_CONTROL_COVERAGE_DEFEATER_ANALYZER-04` — native scenario: measure negative-test and monitoring coverage
- `ELMOS_SECURITY_CONTROL_COVERAGE_DEFEATER_ANALYZER-05` — native scenario: propagate unresolved defeaters to certification

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
