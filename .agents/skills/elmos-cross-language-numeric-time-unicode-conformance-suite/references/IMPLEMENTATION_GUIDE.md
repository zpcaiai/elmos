# Implementation Guide — Cross-Language Numeric, Time and Unicode Conformance Suite

## Purpose

Generate and execute edge-case corpora for overflow, decimal, NaN, timezone, calendar, collation, normalization, grapheme and locale behavior across target languages.

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

1. integer overflow and narrowing corpus
2. decimal and floating-point tolerance corpus
3. DST, leap-second and timezone transition corpus
4. Unicode normalization and grapheme corpus
5. locale/collation and case-folding corpus

## Native acceptance corpus

- `ELMOS_CROSS_LANGUAGE_NUMERIC_TIME_UNICODE_CONFORMANCE_SUITE-01` — native scenario: integer overflow and narrowing corpus
- `ELMOS_CROSS_LANGUAGE_NUMERIC_TIME_UNICODE_CONFORMANCE_SUITE-02` — native scenario: decimal and floating-point tolerance corpus
- `ELMOS_CROSS_LANGUAGE_NUMERIC_TIME_UNICODE_CONFORMANCE_SUITE-03` — native scenario: DST, leap-second and timezone transition corpus
- `ELMOS_CROSS_LANGUAGE_NUMERIC_TIME_UNICODE_CONFORMANCE_SUITE-04` — native scenario: Unicode normalization and grapheme corpus
- `ELMOS_CROSS_LANGUAGE_NUMERIC_TIME_UNICODE_CONFORMANCE_SUITE-05` — native scenario: locale/collation and case-folding corpus

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
