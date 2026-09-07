# Implementation Guide — Privacy Impact, Consent and Purpose-Limitation Verifier

## Purpose

Compile and verify data purpose, legal/organizational basis, consent, minimization, retention, disclosure, provider use and data-subject control across AI workflows.

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

1. Bind every data category and processing step to an approved purpose
2. Verify collection and model/tool disclosure minimization
3. Propagate consent, withdrawal and deletion to derived stores
4. Test provider retention/training settings and cross-border routes
5. Block secondary use and incompatible dataset promotion

## Native acceptance corpus

- `ELMOS_PRIVACY_IMPACT_CONSENT_PURPOSE_VERIFIER-01` — purpose-bound processing
- `ELMOS_PRIVACY_IMPACT_CONSENT_PURPOSE_VERIFIER-02` — consent withdrawal
- `ELMOS_PRIVACY_IMPACT_CONSENT_PURPOSE_VERIFIER-03` — provider no-training setting
- `ELMOS_PRIVACY_IMPACT_CONSENT_PURPOSE_VERIFIER-04` — derived memory deletion
- `ELMOS_PRIVACY_IMPACT_CONSENT_PURPOSE_VERIFIER-05` — cross-border denial
- `ELMOS_PRIVACY_IMPACT_CONSENT_PURPOSE_VERIFIER-06` — secondary-use rejection

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
