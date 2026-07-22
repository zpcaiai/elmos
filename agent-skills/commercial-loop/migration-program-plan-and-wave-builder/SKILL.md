---
name: migration-program-plan-and-wave-builder
description: "Create dependency-aware migration waves tied to capacity, risk, acceptance, and rollback. Use when producing or reviewing this Batch 13 commercial capability."
---

# Migration Program Plan And Wave Builder

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Create dependency-aware migration waves tied to capacity, risk, acceptance, and rollback. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a versioned program plan, wave criteria, dependencies, milestones, gates, and contingency. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass missing owners or baselines, unsafe access, uncontrolled scope, absent acceptance, or hidden delivery failure. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

