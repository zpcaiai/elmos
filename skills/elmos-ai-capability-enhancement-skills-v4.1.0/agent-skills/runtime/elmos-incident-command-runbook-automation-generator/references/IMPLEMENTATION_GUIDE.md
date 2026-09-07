# Implementation Guide — Incident Command and Runbook Automation Generator

## Purpose

Generate role-based incident workflows, diagnostics, communications, mitigations, evidence preservation and recovery gates.

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

1. compile incident taxonomy and severity
2. assign commander, operations and communications roles
3. generate safe diagnostic and mitigation actions
4. preserve evidence and customer timelines
5. gate restart and postmortem recertification

## Native acceptance corpus

- `ELMOS_INCIDENT_COMMAND_RUNBOOK_AUTOMATION_GENERATOR-01` — native scenario: compile incident taxonomy and severity
- `ELMOS_INCIDENT_COMMAND_RUNBOOK_AUTOMATION_GENERATOR-02` — native scenario: assign commander, operations and communications roles
- `ELMOS_INCIDENT_COMMAND_RUNBOOK_AUTOMATION_GENERATOR-03` — native scenario: generate safe diagnostic and mitigation actions
- `ELMOS_INCIDENT_COMMAND_RUNBOOK_AUTOMATION_GENERATOR-04` — native scenario: preserve evidence and customer timelines
- `ELMOS_INCIDENT_COMMAND_RUNBOOK_AUTOMATION_GENERATOR-05` — native scenario: gate restart and postmortem recertification

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
