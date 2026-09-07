# Implementation Guide — Common Criteria Protection Profile Mapper

## Purpose

Implement and independently certify common criteria protection profile mapper, including select applicable collaborative protection profiles and supporting documents, map claimed conformance, selections, assignments and refinements and identify unmet requirements and prohibited overclaim.

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

1. select applicable collaborative protection profiles and supporting documents
2. map claimed conformance, selections, assignments and refinements
3. identify unmet requirements and prohibited overclaim
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_COMMON_CRITERIA_PROTECTION_PROFILE_MAPPER-01` — native scenario: select applicable collaborative protection profiles and supporting documents
- `ELMOS_COMMON_CRITERIA_PROTECTION_PROFILE_MAPPER-02` — native scenario: map claimed conformance, selections, assignments and refinements
- `ELMOS_COMMON_CRITERIA_PROTECTION_PROFILE_MAPPER-03` — native scenario: identify unmet requirements and prohibited overclaim
- `ELMOS_COMMON_CRITERIA_PROTECTION_PROFILE_MAPPER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_COMMON_CRITERIA_PROTECTION_PROFILE_MAPPER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
