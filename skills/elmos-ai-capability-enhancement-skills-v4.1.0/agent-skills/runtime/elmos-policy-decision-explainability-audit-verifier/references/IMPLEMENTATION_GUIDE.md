# Implementation Guide — Policy Decision Explainability and Audit Verifier

## Purpose

Verify that authorization, safety, routing and certification decisions expose policy version, inputs, rationale and counterfactuals without leaking sensitive rules.

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

1. capture policy input and bundle digest
2. produce human/machine explanation
3. verify deterministic replay of decision
4. redact sensitive attributes and rules
5. link recourse and appeal workflow

## Native acceptance corpus

- `ELMOS_POLICY_DECISION_EXPLAINABILITY_AUDIT_VERIFIER-01` — native scenario: capture policy input and bundle digest
- `ELMOS_POLICY_DECISION_EXPLAINABILITY_AUDIT_VERIFIER-02` — native scenario: produce human/machine explanation
- `ELMOS_POLICY_DECISION_EXPLAINABILITY_AUDIT_VERIFIER-03` — native scenario: verify deterministic replay of decision
- `ELMOS_POLICY_DECISION_EXPLAINABILITY_AUDIT_VERIFIER-04` — native scenario: redact sensitive attributes and rules
- `ELMOS_POLICY_DECISION_EXPLAINABILITY_AUDIT_VERIFIER-05` — native scenario: link recourse and appeal workflow

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
