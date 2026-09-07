# Implementation Guide — Internationalization and Localization Conformance Verifier

## Purpose

Verify Unicode, locale, language, timezone, calendar, plural, number, currency, collation, bidirectional text and translated UX across generated projects.

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

1. Separate locale-neutral storage from presentation
2. Test Unicode normalization and grapheme boundaries
3. Verify timezone/DST and calendar transitions
4. Validate plural, gender, number and currency formatting
5. Exercise right-to-left layout, text expansion and fallback

## Native acceptance corpus

- `ELMOS_I18N_L10N_CONFORMANCE_VERIFIER-01` — Unicode normalization
- `ELMOS_I18N_L10N_CONFORMANCE_VERIFIER-02` — DST boundary
- `ELMOS_I18N_L10N_CONFORMANCE_VERIFIER-03` — plural rules
- `ELMOS_I18N_L10N_CONFORMANCE_VERIFIER-04` — currency precision
- `ELMOS_I18N_L10N_CONFORMANCE_VERIFIER-05` — RTL layout
- `ELMOS_I18N_L10N_CONFORMANCE_VERIFIER-06` — missing translation fallback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
