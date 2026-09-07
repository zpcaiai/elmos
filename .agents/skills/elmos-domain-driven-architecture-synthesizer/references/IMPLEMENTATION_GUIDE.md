# Implementation Guide — Domain-Driven Architecture Synthesizer

## Purpose

Recover domains, bounded contexts, aggregates, policies and integration contracts, then generate explicit architecture candidates and trade-offs.

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

1. mine domain language and capability ownership
2. identify bounded contexts and invariants
3. generate context maps and integration patterns
4. compare modular monolith and service options
5. bind decisions to requirements and evidence

## Native acceptance corpus

- `ELMOS_DOMAIN_DRIVEN_ARCHITECTURE_SYNTHESIZER-01` — native scenario: mine domain language and capability ownership
- `ELMOS_DOMAIN_DRIVEN_ARCHITECTURE_SYNTHESIZER-02` — native scenario: identify bounded contexts and invariants
- `ELMOS_DOMAIN_DRIVEN_ARCHITECTURE_SYNTHESIZER-03` — native scenario: generate context maps and integration patterns
- `ELMOS_DOMAIN_DRIVEN_ARCHITECTURE_SYNTHESIZER-04` — native scenario: compare modular monolith and service options
- `ELMOS_DOMAIN_DRIVEN_ARCHITECTURE_SYNTHESIZER-05` — native scenario: bind decisions to requirements and evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
