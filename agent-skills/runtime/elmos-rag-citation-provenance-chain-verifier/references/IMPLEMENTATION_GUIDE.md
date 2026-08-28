# Implementation Guide — RAG Citation Provenance Chain Verifier

## Purpose

Verify every answer claim through chunk, document version, source system, ACL, transformation and retrieval lineage with tamper evidence.

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

1. map claims to exact retrieved spans
2. verify document version and source identity
3. check ACL at query and evidence time
4. detect citation laundering through summaries
5. seal provenance chain and deletion impact

## Native acceptance corpus

- `ELMOS_RAG_CITATION_PROVENANCE_CHAIN_VERIFIER-01` — native scenario: map claims to exact retrieved spans
- `ELMOS_RAG_CITATION_PROVENANCE_CHAIN_VERIFIER-02` — native scenario: verify document version and source identity
- `ELMOS_RAG_CITATION_PROVENANCE_CHAIN_VERIFIER-03` — native scenario: check ACL at query and evidence time
- `ELMOS_RAG_CITATION_PROVENANCE_CHAIN_VERIFIER-04` — native scenario: detect citation laundering through summaries
- `ELMOS_RAG_CITATION_PROVENANCE_CHAIN_VERIFIER-05` — native scenario: seal provenance chain and deletion impact

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
