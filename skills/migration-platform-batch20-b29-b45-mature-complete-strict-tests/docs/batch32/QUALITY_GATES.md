# Batch 32 quality gates

## Certified minimums

A certified client pack requires:

- Exact source and target versions, build tools, providers, browser matrix, and device matrix.
- Runtime fingerprint coverage of at least 95% and a non-placeholder source snapshot digest.
- UI Interaction IR coverage and source-map coverage of at least 95%.
- Real target build and startup pass rate of 100%.
- P0 journey, route, form, authorization, accessibility, visual, cross-browser or device, and performance-budget pass rate of 100%.
- Independent holdout and representative-journey corpora.
- Real evidence references for every certified or supported capability.
- Zero critical unknowns, silent UI drops, route regressions, form regressions, authorization regressions, accessibility regressions, visual regressions, i18n regressions, hydration errors, security or privacy leaks, test-integrity violations, and unapproved dependency changes.

## Test integrity

The gate rejects attempts to obtain green status by:

- deleting, disabling, skipping, or weakening tests;
- auto-updating visual or semantic baselines after target failures;
- broadening screenshot masks, pixel tolerances, accessibility exceptions, or performance budgets after failures;
- removing validation, authorization, CSRF, secure storage, or tenant boundaries;
- hiding behavior with `any`, unsafe assertions, suppressions, client-only checks, or ignored hydration errors;
- testing only isolated components while excluding representative pages or journeys.

## Status rules

- `certified`: all thresholds and zero-critical requirements pass with independent evidence.
- `limited`: bounded useful capability exists but certified scope or evidence is incomplete.
- `experimental`: implementation exists but is not suitable for customer production claims.
- `blocked`: critical behavior or safety requirements cannot be preserved.

Editing JSON status is never sufficient. `run_client_gate.py` is the conservative local source of truth.
