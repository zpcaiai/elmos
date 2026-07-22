---
name: production-topology-and-dependency-inventory
description: "Use when Batch 11 must inventory actual production callers, data, messages, jobs, partners, network, credentials and operational dependencies."
---

# Production Topology And Dependency Inventory

Read `../references/batch-11-production-cutover.md` completely before acting. Use `modules/production-cutover` for PCCM and gate semantics, and validate machine artifacts against `contracts/production-cutover-schema`.

## Required inputs

- Fixed source and Batch 10 P-E/P-F target artifacts, cutover run, observed PCCM phase and approved Wave scope.
- Current Source of Truth, write/read Authority, production topology, data positions and named approvals.
- An approved external production Authority and an append-only evidence workspace outside both repositories.

## Workflow

1. Verify artifact, phase, Wave, stable segment, single-writer, approval and evidence freshness.
2. Inventory actual production callers, data, messages, jobs, partners, network, credentials and operational dependencies.
3. Submit privileged production work only to the named external Authority; do not execute it from the Skill or control plane.
4. Re-observe actual production state, preserve raw references and classify every required result explicitly.

## Fail closed

- Block on registry-only discovery, unknown traffic, direct database access or an ownerless dependency.
- Never skip a PCCM phase, invent a position, average away one failed asset/Wave, approve a waiver or hide an open risk.
- Return `NOT_RUN`, `BLOCKED` or `INCONCLUSIVE` when production evidence is missing; Agent judgment is not production execution evidence.

## Output

Produce time-bound production topology and owned dependency closure list. Bind it to the source/target artifacts, phase, Wave, segment, Authority, production window and approvals. Only the final conformance controller may declare completion, and only from C-G evidence.

