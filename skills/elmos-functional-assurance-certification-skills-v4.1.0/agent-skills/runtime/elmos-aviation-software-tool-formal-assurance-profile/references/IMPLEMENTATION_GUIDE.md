# Implementation Guide — Aviation Software, Tool and Formal Assurance Profile

## Purpose

Implement and independently certify aviation software, tool and formal assurance profile, including compile development assurance level, objectives, independence and traceability, qualify development/verification tools according to certification credit and integrate model-based and formal methods evidence with executable object code verification.

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

1. compile development assurance level, objectives, independence and traceability
2. qualify development/verification tools according to certification credit
3. integrate model-based and formal methods evidence with executable object code verification
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AVIATION_SOFTWARE_TOOL_FORMAL_ASSURANCE_PROFILE-01` — native scenario: compile development assurance level, objectives, independence and traceability
- `ELMOS_AVIATION_SOFTWARE_TOOL_FORMAL_ASSURANCE_PROFILE-02` — native scenario: qualify development/verification tools according to certification credit
- `ELMOS_AVIATION_SOFTWARE_TOOL_FORMAL_ASSURANCE_PROFILE-03` — native scenario: integrate model-based and formal methods evidence with executable object code verification
- `ELMOS_AVIATION_SOFTWARE_TOOL_FORMAL_ASSURANCE_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AVIATION_SOFTWARE_TOOL_FORMAL_ASSURANCE_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
