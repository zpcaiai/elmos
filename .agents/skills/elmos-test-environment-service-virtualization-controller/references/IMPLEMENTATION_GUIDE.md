# Implementation Guide — Test Environment and Service Virtualization Controller

## Purpose

Provision reproducible ephemeral environments, real infrastructure where required, bounded simulators where allowed and explicit fidelity evidence.

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

1. compile environment topology and version lock
2. provision databases, brokers, caches and services
3. separate native, emulated and simulated components
4. inject network and dependency faults
5. destroy safely with evidence and cost accounting

## Native acceptance corpus

- `ELMOS_TEST_ENVIRONMENT_SERVICE_VIRTUALIZATION_CONTROLLER-01` — native scenario: compile environment topology and version lock
- `ELMOS_TEST_ENVIRONMENT_SERVICE_VIRTUALIZATION_CONTROLLER-02` — native scenario: provision databases, brokers, caches and services
- `ELMOS_TEST_ENVIRONMENT_SERVICE_VIRTUALIZATION_CONTROLLER-03` — native scenario: separate native, emulated and simulated components
- `ELMOS_TEST_ENVIRONMENT_SERVICE_VIRTUALIZATION_CONTROLLER-04` — native scenario: inject network and dependency faults
- `ELMOS_TEST_ENVIRONMENT_SERVICE_VIRTUALIZATION_CONTROLLER-05` — native scenario: destroy safely with evidence and cost accounting

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
