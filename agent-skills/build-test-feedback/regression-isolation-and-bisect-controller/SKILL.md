---
name: regression-isolation-and-bisect-controller
description: "Locate a new Batch 8 regression by rollback, dependency-aware patch splitting, and controlled bisection. Use when an applied repair adds failures."
---
# Regression Isolation and Bisect Controller
Read `../references/batch-8-repair-loop.md`. Restore the pre-patch green set, split independent modifications, preserve patch dependency closure and bisect under the same environment. Associate the minimal failing subset with its rule, declaration, dependency or configuration.

Do not bisect on flaky evidence, mix dependency upgrades with other changes, stack more patches before locating the regression, or leave a critical regression outside the last stable Snapshot.
