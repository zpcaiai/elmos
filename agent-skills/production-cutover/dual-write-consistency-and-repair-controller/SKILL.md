---
name: dual-write-consistency-and-repair-controller
description: "Use when Batch 11 must detect and repair missing, divergent, duplicate, out-of-order and delete inconsistencies."
---

# Dual Write Consistency And Repair Controller

Read `../references/batch-11-production-cutover.md` completely before acting. Use `modules/production-cutover` for PCCM and gate semantics, and validate machine artifacts against `contracts/production-cutover-schema`.

## Required inputs

- Fixed source and Batch 10 P-E/P-F target artifacts, cutover run, observed PCCM phase and approved Wave scope.
- Current Source of Truth, write/read Authority, production topology, data positions and named approvals.
- An approved external production Authority and an append-only evidence workspace outside both repositories.

## Workflow

1. Verify artifact, phase, Wave, stable segment, single-writer, approval and evidence freshness.
2. Detect and repair missing, divergent, duplicate, out-of-order and delete inconsistencies.
3. Submit privileged production work only to the named external Authority; do not execute it from the Skill or control plane.
4. Re-observe actual production state, preserve raw references and classify every required result explicitly.

## Fail closed

- Block on silent last-write-wins, non-authoritative overwrite, repeated external effect or unresolved conflict.
- Never skip a PCCM phase, invent a position, average away one failed asset/Wave, approve a waiver or hide an open risk.
- Return `NOT_RUN`, `BLOCKED` or `INCONCLUSIVE` when production evidence is missing; Agent judgment is not production execution evidence.

## Output

Produce comparison ledger, safe repair decision and post-repair reconciliation. Bind it to the source/target artifacts, phase, Wave, segment, Authority, production window and approvals. Only the final conformance controller may declare completion, and only from C-G evidence.

