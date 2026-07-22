---
name: mutation-testing-and-test-effectiveness-analyzer
description: Normalize incremental Java, .NET, Python, and JavaScript mutation testing and analyze whether tests detect seeded faults. Use for assertion-strength evidence, survived mutants, mutation gates, or AI test candidate inputs.
---

# Mutation Testing and Effectiveness Analysis

## Select an adapter

Use capability-checked Java PIT, .NET/JavaScript Stryker, Python mutation, or custom IR providers. Pin tool and runner versions. Never mutate a production artifact or execute mutation against production services.

## Normalize results

Support conditional boundary, negated condition, return value, removed call, arithmetic, logical, null, exception, loop, constant, and async mutations. Normalize each mutant as killed, survived, no coverage, timeout, non-viable, run error, or equivalent candidate.

## Report distinct metrics

Report mutation coverage, test strength, and overall mutation score separately. Do not substitute line coverage for effectiveness. Slice gates by critical domain, changed/new code, core algorithm, utility, and generated code rather than applying one system-wide score.

## Control cost

For pull requests, mutate changed symbols, related critical domains, and recently survived mutants. Expand scope on merge/nightly. Enforce CPU/time budgets, isolated mutants, cancellation, timeouts, and cache provenance.

## Handle uncertainty

Route suspected equivalent mutants to human confirmation; never auto-exclude or auto-penalize them. Link every survived mutant to affected rules, existing tests, missing assertions, suggested test type, risk, and optional AI test candidate.
