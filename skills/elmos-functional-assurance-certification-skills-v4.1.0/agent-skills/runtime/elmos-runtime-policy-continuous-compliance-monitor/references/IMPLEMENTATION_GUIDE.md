# Implementation Guide — Runtime Policy Continuous Compliance Monitor

## Purpose

Evaluate deployed configuration, identity, network, data, model and evidence state continuously against versioned policies and certification scope.

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

1. collect attested runtime state
2. evaluate drift and control effectiveness
3. distinguish transient from persistent violation
4. trigger containment, evidence invalidation and recertification
5. report scope and policy version

## Native acceptance corpus

- `ELMOS_RUNTIME_POLICY_CONTINUOUS_COMPLIANCE_MONITOR-01` — native scenario: collect attested runtime state
- `ELMOS_RUNTIME_POLICY_CONTINUOUS_COMPLIANCE_MONITOR-02` — native scenario: evaluate drift and control effectiveness
- `ELMOS_RUNTIME_POLICY_CONTINUOUS_COMPLIANCE_MONITOR-03` — native scenario: distinguish transient from persistent violation
- `ELMOS_RUNTIME_POLICY_CONTINUOUS_COMPLIANCE_MONITOR-04` — native scenario: trigger containment, evidence invalidation and recertification
- `ELMOS_RUNTIME_POLICY_CONTINUOUS_COMPLIANCE_MONITOR-05` — native scenario: report scope and policy version

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
