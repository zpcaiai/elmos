# Implementation Guide — Dependency Update and Renovation Controller

## Purpose

Continuously propose, test and promote dependency, framework and toolchain upgrades with semantic impact, security and rollback evidence.

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

1. detect releases, advisories and EOL
2. compute repository and generated-code impact
3. open bounded upgrade changes
4. run native, differential and security suites
5. promote, defer or rollback with rationale

## Native acceptance corpus

- `ELMOS_DEPENDENCY_UPDATE_RENOVATION_CONTROLLER-01` — native scenario: detect releases, advisories and EOL
- `ELMOS_DEPENDENCY_UPDATE_RENOVATION_CONTROLLER-02` — native scenario: compute repository and generated-code impact
- `ELMOS_DEPENDENCY_UPDATE_RENOVATION_CONTROLLER-03` — native scenario: open bounded upgrade changes
- `ELMOS_DEPENDENCY_UPDATE_RENOVATION_CONTROLLER-04` — native scenario: run native, differential and security suites
- `ELMOS_DEPENDENCY_UPDATE_RENOVATION_CONTROLLER-05` — native scenario: promote, defer or rollback with rationale

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
