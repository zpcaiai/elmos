---
name: business-technical-security-and-operations-acceptance
description: "Use when Batch 11 must collect independent business, engineering, security, operations and compliance acceptance."
---

# Business Technical Security And Operations Acceptance

Read `../references/batch-11-production-cutover.md` completely before acting. Use `modules/production-cutover` for PCCM and gate semantics, and validate machine artifacts against `contracts/production-cutover-schema`.

## Required inputs

- Fixed source and Batch 10 P-E/P-F target artifacts, cutover run, observed PCCM phase and approved Wave scope.
- Current Source of Truth, write/read Authority, production topology, data positions and named approvals.
- An approved external production Authority and an append-only evidence workspace outside both repositories.

## Workflow

1. Verify artifact, phase, Wave, stable segment, single-writer, approval and evidence freshness.
2. Collect independent business, engineering, security, operations and compliance acceptance.
3. Submit privileged production work only to the named external Authority; do not execute it from the Skill or control plane.
4. Re-observe actual production state, preserve raw references and classify every required result explicitly.

## Fail closed

- Block on proxy sign-off, oral approval, conditional critical risk or expired acceptance.
- Never skip a PCCM phase, invent a position, average away one failed asset/Wave, approve a waiver or hide an open risk.
- Return `NOT_RUN`, `BLOCKED` or `INCONCLUSIVE` when production evidence is missing; Agent judgment is not production execution evidence.

## Output

Produce artifact- and phase-bound sign-offs with evidence, owner, conditions and expiry. Bind it to the source/target artifacts, phase, Wave, segment, Authority, production window and approvals. Only the final conformance controller may declare completion, and only from C-G evidence.

