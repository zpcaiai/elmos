# Implementation Guide — A2A v1 Agent Card Trust Compiler

## Purpose

Compile, sign, verify, rotate and revoke A2A v1 Agent Cards that bind identity, capabilities, interfaces, tenant scope and trust evidence.

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

1. Canonical Agent Card generation
2. Signature and issuer trust validation
3. Protocol/interface version negotiation
4. Tenant and trust-domain binding
5. Expiry, rotation, revocation and evidence-root binding

## Native acceptance corpus

- `ELMOS_A2A_V1_AGENT_CARD_TRUST_COMPILER-01` — signed card verification
- `ELMOS_A2A_V1_AGENT_CARD_TRUST_COMPILER-02` — tampered card rejection
- `ELMOS_A2A_V1_AGENT_CARD_TRUST_COMPILER-03` — expired card rejection
- `ELMOS_A2A_V1_AGENT_CARD_TRUST_COMPILER-04` — interface negotiation
- `ELMOS_A2A_V1_AGENT_CARD_TRUST_COMPILER-05` — tenant mismatch rejection
- `ELMOS_A2A_V1_AGENT_CARD_TRUST_COMPILER-06` — revocation propagation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
