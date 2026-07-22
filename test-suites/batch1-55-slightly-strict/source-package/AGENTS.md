# ELMOS Slightly Strict Test Suite — Agent Rules

1. Read installed Batch manifests before generating tests.
2. Never claim a Batch is certified from static Skill validation.
3. P0 failures block release.
4. Do not count skipped, quarantined or expected-failure tests as passed.
5. Do not weaken assertions, thresholds or tenant/security checks to make a gate green.
6. Preserve source snapshots, environment versions, seeds, raw outputs and counterexamples.
7. Provider-specific claims require real provider sandbox or approved emulator evidence.
8. Use synthetic or approved test data; never copy production secrets into fixtures.
9. Flaky tests are defects. Quarantine is temporary and expires within seven days.
10. A waiver must be scoped, approved, expiring and include compensating controls.
11. Cross-tenant access, secret leakage, duplicate payments, unbalanced journals,
    clinical/industrial safety bypass and irreversible data loss are non-waivable by default.
12. Stop when the installed Batch scope cannot be resolved reliably.
