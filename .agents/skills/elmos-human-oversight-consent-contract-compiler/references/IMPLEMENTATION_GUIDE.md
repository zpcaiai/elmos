# Implementation Guide — Human Oversight and Consent Contract Compiler

## Purpose

Compile auditable human oversight contracts for high-risk decisions, dual control, consent scope, approval TTL, escalation, revocation and parameter binding.

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

1. Risk-tiered approval policy
2. Four-eyes and role separation
3. Approval evidence and exact parameter binding
4. TTL, escalation, delegation and revocation
5. Replay-resistant approval lifecycle

## Native acceptance corpus

- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-01` — single approval
- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-02` — dual control
- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-03` — expired approval
- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-04` — parameter mismatch
- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-05` — revoked approval
- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-06` — escalation timeout
- `ELMOS_HUMAN_OVERSIGHT_CONSENT_CONTRACT_COMPILER-07` — approval replay denial

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
