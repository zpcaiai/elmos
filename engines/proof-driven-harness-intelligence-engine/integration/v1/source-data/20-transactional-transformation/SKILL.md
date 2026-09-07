---
name: elmos-transactional-semantic-transformation
description: Perform stale-safe semantic mutations with explicit preconditions, postconditions, rollback, and evidence.
priority: P0
---

# K2 — Transactional Semantic Transformation

## Skills

- semantic-anchor
- content-hash-anchor
- symbol-identity-anchor
- stale-state-detector
- read-set-tracker
- write-set-tracker
- patch-intent-contract
- edit-precondition-validator
- semantic-conflict-detector
- ast-structural-rewrite
- semantic-ir-rewrite
- framework-aware-rewrite
- edit-postcondition-validator
- transactional-patch
- snapshot-manager
- rollback-manager
- atomic-commit-planner
- dependency-aware-commit-ordering
- semantic-merge-validator
- merge-proof-generator

## Routing

1. Semantic IR rewrite when a route is modeled.
2. Compiler/LSP refactor where supported.
3. AST structural rewrite.
4. Anchored textual patch only for syntax-neutral cases.
5. Raw search/replace is last-resort and requires explicit evidence.

## Transaction lifecycle

PREPARED → PRECONDITIONS_VALID → APPLIED → VERIFIED → COMMITTED

Failure paths:

PRECONDITION_FAILED
APPLY_FAILED
POSTCONDITION_FAILED
CONFLICTED
ROLLED_BACK
QUARANTINED

## Production rules

- A stale anchor MUST reject mutation.
- A changed exported symbol MUST trigger reference-integrity verification.
- A framework-semantic rewrite MUST name the mapping rule used.
- Merge MUST re-run relevant postconditions against merged revision.
- Rollback MUST be executable without model reasoning.

## Acceptance

- no patch applies against stale semantic identity;
- deterministic rollback for every committed bounded transaction;
- first-pass edit success and repair-loop counts are measured;
- merged output is re-certified, not assumed equivalent to child outputs.
