---
name: behavioral-scenario-and-input-corpus-builder
description: "Build versioned Batch 9 differential scenarios and input corpora from tests, contracts, incidents, sanitized traffic, boundaries and obligations. Use when coverage or replay inputs must be created."
---

# Behavioral Scenario and Input Corpus Builder

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Inventory source tests, public contracts, message/database constraints, incidents and reviewed samples.
2. Generate success, error, security, transaction, time, retry, concurrency, null/empty and precision cases.
3. Bind each scenario to initial state, input, expected observations, Oracles, criticality and obligations.

## Hard rules

- Map every blocking obligation to a scenario.
- Remove credentials and sanitize production-derived data.
- Save random seeds and ensure every scenario is independently repeatable.

## Output

Emit queryable scenario and corpus records by module, origin, risk and obligation.

