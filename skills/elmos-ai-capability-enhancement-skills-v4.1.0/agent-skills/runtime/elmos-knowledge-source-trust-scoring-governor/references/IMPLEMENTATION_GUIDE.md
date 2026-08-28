# Implementation Guide — Knowledge Source Trust Scoring Governor

## Purpose

Govern source identity, ownership, editorial quality, freshness, corroboration, conflict and revocation signals without turning heuristic trust into proof.

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

1. register source identity and governance metadata
2. compute bounded trust signals with explanations
3. separate trust, relevance and recency
4. propagate revocation and incident history
5. require authoritative review for critical domains

## Native acceptance corpus

- `ELMOS_KNOWLEDGE_SOURCE_TRUST_SCORING_GOVERNOR-01` — native scenario: register source identity and governance metadata
- `ELMOS_KNOWLEDGE_SOURCE_TRUST_SCORING_GOVERNOR-02` — native scenario: compute bounded trust signals with explanations
- `ELMOS_KNOWLEDGE_SOURCE_TRUST_SCORING_GOVERNOR-03` — native scenario: separate trust, relevance and recency
- `ELMOS_KNOWLEDGE_SOURCE_TRUST_SCORING_GOVERNOR-04` — native scenario: propagate revocation and incident history
- `ELMOS_KNOWLEDGE_SOURCE_TRUST_SCORING_GOVERNOR-05` — native scenario: require authoritative review for critical domains

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
