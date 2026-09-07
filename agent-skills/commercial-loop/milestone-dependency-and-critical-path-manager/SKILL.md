---
name: milestone-dependency-and-critical-path-manager
description: "Control milestone baselines, dependencies, critical paths, slippage, and recovery decisions. Use when producing or reviewing this Batch 13 commercial capability."
---

# Milestone Dependency And Critical Path Manager

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Control milestone baselines, dependencies, critical paths, slippage, and recovery decisions. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a networked milestone plan, variance, impacts, recovery options, owner, and approval. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass missing owners or baselines, unsafe access, uncontrolled scope, absent acceptance, or hidden delivery failure. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

