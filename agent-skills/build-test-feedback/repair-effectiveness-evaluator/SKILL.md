---
name: repair-effectiveness-evaluator
description: "Evaluate a Batch 8 patch as effective, partial, neutral, regressive, unsafe, or inconclusive. Use after affected and regression validation."
---
# Repair Effectiveness Evaluator
Read `../references/batch-8-repair-loop.md`. Compare cluster closure, blocking/compile diagnostics, required tests, new errors, obligations, patch size, contracts, suppression/dynamic deltas, cost and duration.

Treat security/public-contract regression, test deletion, assertion weakening, casts/dynamic, exception swallowing, fixed returns or analyzer disabling as unsafe even when error count drops. Roll back unsafe/regressive patches and avoid repeating neutral attempts.
