# Implementation Guide — Software Update Trust Root Governor

## Purpose

Secure Skill, adapter, policy, model-profile and runtime updates using threshold roles, delegated trust, rollback/freeze protection and signed metadata.

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

1. Manage root/targets/snapshot/timestamp style roles
2. Use threshold signing and offline root procedures
3. Delegate targets by ecosystem and risk
4. Prevent rollback and freeze attacks
5. Rotate/revoke keys with continuity evidence

## Native acceptance corpus

- `ELMOS_SOFTWARE_UPDATE_TRUST_ROOT_GOVERNOR-01` — valid signed update
- `ELMOS_SOFTWARE_UPDATE_TRUST_ROOT_GOVERNOR-02` — expired timestamp rejected
- `ELMOS_SOFTWARE_UPDATE_TRUST_ROOT_GOVERNOR-03` — rollback version rejected
- `ELMOS_SOFTWARE_UPDATE_TRUST_ROOT_GOVERNOR-04` — threshold signature
- `ELMOS_SOFTWARE_UPDATE_TRUST_ROOT_GOVERNOR-05` — delegated target scope
- `ELMOS_SOFTWARE_UPDATE_TRUST_ROOT_GOVERNOR-06` — root rotation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
