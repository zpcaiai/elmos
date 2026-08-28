# Implementation Guide — Assurance Case Confidence Quantifier

## Purpose

Implement and independently certify assurance case confidence quantifier, including score evidence relevance, sufficiency, independence, diversity, freshness and uncertainty, propagate confidence and unresolved defeaters through claim argument graph and prevent numeric confidence from replacing hard critical gates.

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

1. score evidence relevance, sufficiency, independence, diversity, freshness and uncertainty
2. propagate confidence and unresolved defeaters through claim argument graph
3. prevent numeric confidence from replacing hard critical gates
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_ASSURANCE_CASE_CONFIDENCE_QUANTIFIER-01` — native scenario: score evidence relevance, sufficiency, independence, diversity, freshness and uncertainty
- `ELMOS_ASSURANCE_CASE_CONFIDENCE_QUANTIFIER-02` — native scenario: propagate confidence and unresolved defeaters through claim argument graph
- `ELMOS_ASSURANCE_CASE_CONFIDENCE_QUANTIFIER-03` — native scenario: prevent numeric confidence from replacing hard critical gates
- `ELMOS_ASSURANCE_CASE_CONFIDENCE_QUANTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_ASSURANCE_CASE_CONFIDENCE_QUANTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
