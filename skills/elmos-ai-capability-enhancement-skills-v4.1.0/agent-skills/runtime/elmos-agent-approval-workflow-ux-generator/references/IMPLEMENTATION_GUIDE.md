# Implementation Guide — Agent Approval Workflow UX Generator

## Purpose

Generate clear preview, diff, risk, evidence, confirmation, expiry, rejection and recovery interfaces for human-controlled actions.

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

1. compile approval contract to UI states
2. display exact action and affected resources
3. bind approval digest to tool parameters
4. support dual control, timeout and escalation
5. test accessibility, comprehension and replay resistance

## Native acceptance corpus

- `ELMOS_AGENT_APPROVAL_WORKFLOW_UX_GENERATOR-01` — native scenario: compile approval contract to UI states
- `ELMOS_AGENT_APPROVAL_WORKFLOW_UX_GENERATOR-02` — native scenario: display exact action and affected resources
- `ELMOS_AGENT_APPROVAL_WORKFLOW_UX_GENERATOR-03` — native scenario: bind approval digest to tool parameters
- `ELMOS_AGENT_APPROVAL_WORKFLOW_UX_GENERATOR-04` — native scenario: support dual control, timeout and escalation
- `ELMOS_AGENT_APPROVAL_WORKFLOW_UX_GENERATOR-05` — native scenario: test accessibility, comprehension and replay resistance

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
