---
name: compatibility-window-and-expand-contract-planner
description: Plan expand-contract compatibility windows, multi-version behavior, usage observation, expiry, and removal tasks. Use when old and new consumers or producers must coexist.
---

# Compatibility Window and Expand-Contract Planner

## Workflow

1. Bind each window to organization, contract, old/new versions, owner, start, expiry, supported combinations, strategies, rollback period, and removal task.
2. Prefer additive expansion: optional fields, tolerant readers, dual-version endpoints, versioned topics, upcast/downcast, compatibility views, or SDK facades.
3. Observe old-version traffic per known and unknown consumer throughout the required window.
4. Keep rollback compatibility until the rollback window ends.
5. At expiry, return `EXPIRED_WITH_USAGE` whenever old use remains; do not silently extend or close.
6. Permit contract removal only after zero old use, external-consumer confirmation, complete observation, ended rollback window, owner approval, and immutable evidence.

## Outputs

Emit window versions, strategies, supported combinations, usage evidence, expiry alerts, removal tasks, and closure blockers. Every compatibility layer must have an owner and removal date.
