# Implementation Guide — Certification Transparency Log and Notary

## Purpose

Publish append-only, privacy-safe certificate, revocation, signer and evidence-root events with inclusion and consistency proofs for independent verification.

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

1. Append certificate and revocation commitments
2. Provide inclusion and consistency proofs
3. Minimize customer-sensitive metadata
4. Cross-sign checkpoints or external timestamps
5. Detect split-view and missing publication

## Native acceptance corpus

- `ELMOS_CERTIFICATION_TRANSPARENCY_LOG_NOTARY-01` — certificate inclusion proof
- `ELMOS_CERTIFICATION_TRANSPARENCY_LOG_NOTARY-02` — revocation inclusion
- `ELMOS_CERTIFICATION_TRANSPARENCY_LOG_NOTARY-03` — checkpoint consistency
- `ELMOS_CERTIFICATION_TRANSPARENCY_LOG_NOTARY-04` — offline verification bundle
- `ELMOS_CERTIFICATION_TRANSPARENCY_LOG_NOTARY-05` — privacy redaction
- `ELMOS_CERTIFICATION_TRANSPARENCY_LOG_NOTARY-06` — split-view detection

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
