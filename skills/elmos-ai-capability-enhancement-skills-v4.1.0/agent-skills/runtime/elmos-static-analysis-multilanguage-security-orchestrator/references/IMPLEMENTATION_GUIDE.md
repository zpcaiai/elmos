# Implementation Guide — Multi-Language Static Analysis and Security Orchestrator

## Purpose

Route compiler diagnostics, SAST, dependency, secret, IaC and custom semantic analyses across generated polyglot repositories with normalized evidence.

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

1. select analyzers by language/framework/risk
2. pin rule packs and tool digests
3. normalize findings without losing provenance
4. deduplicate and correlate cross-language flows
5. gate suppressions and false-positive waivers

## Native acceptance corpus

- `ELMOS_STATIC_ANALYSIS_MULTILANGUAGE_SECURITY_ORCHESTRATOR-01` — native scenario: select analyzers by language/framework/risk
- `ELMOS_STATIC_ANALYSIS_MULTILANGUAGE_SECURITY_ORCHESTRATOR-02` — native scenario: pin rule packs and tool digests
- `ELMOS_STATIC_ANALYSIS_MULTILANGUAGE_SECURITY_ORCHESTRATOR-03` — native scenario: normalize findings without losing provenance
- `ELMOS_STATIC_ANALYSIS_MULTILANGUAGE_SECURITY_ORCHESTRATOR-04` — native scenario: deduplicate and correlate cross-language flows
- `ELMOS_STATIC_ANALYSIS_MULTILANGUAGE_SECURITY_ORCHESTRATOR-05` — native scenario: gate suppressions and false-positive waivers

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
