# Implementation Guide — Compiler and Codemod Rule Corpus Governor

## Purpose

Curate deterministic rewrite rules, fixtures, semantic preservation contracts, provenance, coverage, conflict handling and promotion across language routes.

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

1. version rules with pre/postconditions
2. maintain positive, negative and conflict fixtures
3. measure construct and repository coverage
4. promote counterexample-derived rules under review
5. revoke rules after compiler or runtime drift

## Native acceptance corpus

- `ELMOS_COMPILER_CODEMOD_RULE_CORPUS_GOVERNOR-01` — native scenario: version rules with pre/postconditions
- `ELMOS_COMPILER_CODEMOD_RULE_CORPUS_GOVERNOR-02` — native scenario: maintain positive, negative and conflict fixtures
- `ELMOS_COMPILER_CODEMOD_RULE_CORPUS_GOVERNOR-03` — native scenario: measure construct and repository coverage
- `ELMOS_COMPILER_CODEMOD_RULE_CORPUS_GOVERNOR-04` — native scenario: promote counterexample-derived rules under review
- `ELMOS_COMPILER_CODEMOD_RULE_CORPUS_GOVERNOR-05` — native scenario: revoke rules after compiler or runtime drift

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
