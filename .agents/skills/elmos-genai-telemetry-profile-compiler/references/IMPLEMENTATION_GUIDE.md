# Implementation Guide — GenAI Telemetry Profile Compiler

## Purpose

Compile versioned OpenTelemetry/OpenInference-compatible GenAI traces, metrics and logs with privacy, cardinality, sampling, cost and evidence-binding rules.

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

1. Versioned semantic convention profile
2. Trace/model/tool/retrieval correlation
3. PII and secret redaction
4. Cardinality and sampling budgets
5. Cost, evidence and tenant binding

## Native acceptance corpus

- `ELMOS_GENAI_TELEMETRY_PROFILE_COMPILER-01` — trace completeness
- `ELMOS_GENAI_TELEMETRY_PROFILE_COMPILER-02` — semantic version lock
- `ELMOS_GENAI_TELEMETRY_PROFILE_COMPILER-03` — PII redaction
- `ELMOS_GENAI_TELEMETRY_PROFILE_COMPILER-04` — high-cardinality guard
- `ELMOS_GENAI_TELEMETRY_PROFILE_COMPILER-05` — sampling reproducibility
- `ELMOS_GENAI_TELEMETRY_PROFILE_COMPILER-06` — cost correlation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
