---
name: batch-11-final-conformance-and-project-closure-gate
description: "Use when Batch 11 must evaluate C-A through C-G and decide whether the migration project is truly complete."
---

# Batch 11 Final Conformance And Project Closure Gate

Read `../references/batch-11-production-cutover.md` completely before acting. Use `modules/production-cutover` for PCCM and gate semantics, and validate machine artifacts against `contracts/production-cutover-schema`.

## Required inputs

- Fixed source and Batch 10 P-E/P-F target artifacts, cutover run, observed PCCM phase and approved Wave scope.
- Current Source of Truth, write/read Authority, production topology, data positions and named approvals.
- An approved external production Authority and an append-only evidence workspace outside both repositories.

## Workflow

1. Verify artifact, phase, Wave, stable segment, single-writer, approval and evidence freshness.
2. Evaluate C-A through C-G and decide whether the migration project is truly complete.
3. Submit privileged production work only to the named external Authority; do not execute it from the Skill or control plane.
4. Re-observe actual production state, preserve raw references and classify every required result explicitly.

## Fail closed

- Block on unmigrated truth, dual writer, data/message/job loss, incomplete acceptance, unsafe retirement or missing pack.
- Never skip a PCCM phase, invent a position, average away one failed asset/Wave, approve a waiver or hide an open risk.
- Return `NOT_RUN`, `BLOCKED` or `INCONCLUSIVE` when production evidence is missing; Agent judgment is not production execution evidence.

## Output

Produce per-domain conformance, exact highest Gate and evidence-bound closure decision. Bind it to the source/target artifacts, phase, Wave, segment, Authority, production window and approvals. Only the final conformance controller may declare completion, and only from C-G evidence.

