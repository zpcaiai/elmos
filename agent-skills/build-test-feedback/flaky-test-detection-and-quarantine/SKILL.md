---
name: flaky-test-detection-and-quarantine
description: "Detect nondeterministic Batch 8 tests and manage temporary accountable quarantine. Use when repeated, reordered, isolated, time-, seed-, port-, or state-sensitive runs disagree."
---
# Flaky Test Detection and Quarantine
Read `../references/batch-8-repair-loop.md`. Record run counts, pass/fail distribution, suspected cause, owner, temporary status and expiry. Continue running quarantined tests in a separate report and exclude them from stable pass rate.

Do not count retry-then-pass as stable, retry indefinitely, create permanent quarantine, quarantine critical security/transaction tests, or close a Semantic Obligation with flaky evidence.
