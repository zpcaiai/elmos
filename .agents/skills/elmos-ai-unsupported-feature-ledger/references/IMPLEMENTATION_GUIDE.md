# Implementation Guide — AIUnsupportedFeatureLedger

## Purpose

Record every unsupported, partially represented, emulated, runtime-monitored or waived feature and block silent degradation.

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

1. Compile governance into executable controls
2. Bind decisions to evidence and human authority
3. Track waivers, expiry and residual risk
4. Prevent policy and completion self-certification

## Native acceptance corpus

- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-01` — allow
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-02` — deny
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-03` — unknown policy
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-04` — revocation
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-05` — AiUnsupportedFeatureLedger representative end-to-end fixture
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-06` — crash recovery preserves single-writer semantics
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-07` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-08` — undeclared authority is denied
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-09` — resource and wall-clock budget is measured
- `ELMOS_AI_UNSUPPORTED_FEATURE_LEDGER-10` — allow/deny/unknown

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
