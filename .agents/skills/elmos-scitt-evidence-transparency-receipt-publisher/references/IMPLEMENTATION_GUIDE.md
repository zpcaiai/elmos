# Implementation Guide — SCITT Evidence Transparency Receipt Publisher

## Purpose

Publish signed evidence statements and verification receipts to an append-only transparency service while preserving tenant privacy, revocation and certificate lineage.

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

1. canonicalize signed evidence statements
2. publish and verify transparency receipts
3. bind receipts to Evidence Merkle roots and certificate scope
4. support revocation and re-publication without history rewrite
5. apply tenant disclosure and redaction policy

## Native acceptance corpus

- `ELMOS_SCITT_EVIDENCE_TRANSPARENCY_RECEIPT_PUBLISHER-01` — native scenario: canonicalize signed evidence statements
- `ELMOS_SCITT_EVIDENCE_TRANSPARENCY_RECEIPT_PUBLISHER-02` — native scenario: publish and verify transparency receipts
- `ELMOS_SCITT_EVIDENCE_TRANSPARENCY_RECEIPT_PUBLISHER-03` — native scenario: bind receipts to Evidence Merkle roots and certificate scope
- `ELMOS_SCITT_EVIDENCE_TRANSPARENCY_RECEIPT_PUBLISHER-04` — native scenario: support revocation and re-publication without history rewrite
- `ELMOS_SCITT_EVIDENCE_TRANSPARENCY_RECEIPT_PUBLISHER-05` — native scenario: apply tenant disclosure and redaction policy

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
