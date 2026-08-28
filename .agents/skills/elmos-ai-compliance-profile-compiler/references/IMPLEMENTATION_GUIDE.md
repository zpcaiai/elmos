# Implementation Guide — AI Compliance Profile Compiler

## Purpose

Compile jurisdiction, industry and customer control profiles into executable policies, evidence requirements, human decisions and unresolved legal obligations.

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

1. Control framework mapping
2. Jurisdiction and deployment-context selection
3. Policy/evidence/human-decision compilation
4. Conflict and gap analysis
5. No automatic legal-certification boundary

## Native acceptance corpus

- `ELMOS_AI_COMPLIANCE_PROFILE_COMPILER-01` — profile selection
- `ELMOS_AI_COMPLIANCE_PROFILE_COMPILER-02` — control mapping
- `ELMOS_AI_COMPLIANCE_PROFILE_COMPILER-03` — conflicting obligations
- `ELMOS_AI_COMPLIANCE_PROFILE_COMPILER-04` — missing evidence block
- `ELMOS_AI_COMPLIANCE_PROFILE_COMPILER-05` — regional restriction
- `ELMOS_AI_COMPLIANCE_PROFILE_COMPILER-06` — human legal decision required

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
