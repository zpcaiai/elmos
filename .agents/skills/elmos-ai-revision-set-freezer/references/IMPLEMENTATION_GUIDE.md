# Implementation Guide — AIRevisionSetFreezer

## Purpose

Freeze the exact source, requirements, AI-SIR, target profiles, model/tool policies, adapter digests, templates, data sets and verification configuration used by a generation run.

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

1. Bind every run to exact Goal and RevisionSet
2. Compile durable control state and terminal semantics
3. Enforce fail-closed gates and independent completion authority
4. Expose pause/resume/cancel/replan with auditable events

## Native acceptance corpus

- `ELMOS_AI_REVISION_SET_FREEZER-01` — round-trip fixture
- `ELMOS_AI_REVISION_SET_FREEZER-02` — unsupported construct
- `ELMOS_AI_REVISION_SET_FREEZER-03` — source map integrity
- `ELMOS_AI_REVISION_SET_FREEZER-04` — AiRevisionSetFreezer representative end-to-end fixture
- `ELMOS_AI_REVISION_SET_FREEZER-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_REVISION_SET_FREEZER-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_REVISION_SET_FREEZER-07` — undeclared authority is denied
- `ELMOS_AI_REVISION_SET_FREEZER-08` — resource and wall-clock budget is measured
- `ELMOS_AI_REVISION_SET_FREEZER-09` — exact revision binding
- `ELMOS_AI_REVISION_SET_FREEZER-10` — pause/resume/cancel

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
