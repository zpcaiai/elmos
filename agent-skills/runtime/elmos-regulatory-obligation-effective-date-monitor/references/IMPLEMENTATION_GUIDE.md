# Implementation Guide — Regulatory Obligation and Effective-Date Monitor

## Purpose

Track versioned jurisdictional obligations, effective dates, guidance and product scope; trigger human legal review and technical control changes.

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

1. maintain authoritative source and jurisdiction registry
2. model applicability and effective dates
3. diff obligation/control mappings
4. open reviewed implementation and evidence changes
5. block claims when legal interpretation unresolved

## Native acceptance corpus

- `ELMOS_REGULATORY_OBLIGATION_EFFECTIVE_DATE_MONITOR-01` — native scenario: maintain authoritative source and jurisdiction registry
- `ELMOS_REGULATORY_OBLIGATION_EFFECTIVE_DATE_MONITOR-02` — native scenario: model applicability and effective dates
- `ELMOS_REGULATORY_OBLIGATION_EFFECTIVE_DATE_MONITOR-03` — native scenario: diff obligation/control mappings
- `ELMOS_REGULATORY_OBLIGATION_EFFECTIVE_DATE_MONITOR-04` — native scenario: open reviewed implementation and evidence changes
- `ELMOS_REGULATORY_OBLIGATION_EFFECTIVE_DATE_MONITOR-05` — native scenario: block claims when legal interpretation unresolved

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
