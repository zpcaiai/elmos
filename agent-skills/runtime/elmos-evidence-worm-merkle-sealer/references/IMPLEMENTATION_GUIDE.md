# Implementation Guide — Evidence WORM and Merkle Sealer

## Purpose

Seal commands, inputs, artifacts, traces, proof results and approvals into immutable evidence bundles with chain of custody, Merkle roots, retention and legal hold.

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

1. Canonicalize and hash evidence objects
2. Build claim-to-evidence graph and Merkle tree
3. Write to WORM/content-addressed storage
4. Record custody, access and redaction events
5. Support retention, legal hold and verified export

## Native acceptance corpus

- `ELMOS_EVIDENCE_WORM_MERKLE_SEALER-01` — bundle seal/verify
- `ELMOS_EVIDENCE_WORM_MERKLE_SEALER-02` — single-byte tamper rejection
- `ELMOS_EVIDENCE_WORM_MERKLE_SEALER-03` — missing evidence node detection
- `ELMOS_EVIDENCE_WORM_MERKLE_SEALER-04` — custody transfer
- `ELMOS_EVIDENCE_WORM_MERKLE_SEALER-05` — retention expiry policy
- `ELMOS_EVIDENCE_WORM_MERKLE_SEALER-06` — legal hold prevents deletion

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
