# Implementation Guide — Localization and Cultural Policy Adapter

## Purpose

Adapt generated language, UI, examples, safety and workflow policy to locale while preserving core semantics and avoiding unsupported cultural assumptions.

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

1. compile locale, terminology and formatting profile
2. adapt prompts, UI and examples
3. verify bidirectional text and input methods
4. apply jurisdictional content/consent differences
5. test semantic parity and human review

## Native acceptance corpus

- `ELMOS_LOCALIZATION_CULTURAL_POLICY_ADAPTER-01` — native scenario: compile locale, terminology and formatting profile
- `ELMOS_LOCALIZATION_CULTURAL_POLICY_ADAPTER-02` — native scenario: adapt prompts, UI and examples
- `ELMOS_LOCALIZATION_CULTURAL_POLICY_ADAPTER-03` — native scenario: verify bidirectional text and input methods
- `ELMOS_LOCALIZATION_CULTURAL_POLICY_ADAPTER-04` — native scenario: apply jurisdictional content/consent differences
- `ELMOS_LOCALIZATION_CULTURAL_POLICY_ADAPTER-05` — native scenario: test semantic parity and human review

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
