---
name: frontend-client-engine-contract-and-worker
description: Operate the isolated TypeScript frontend/client engine contract for Web, desktop, and mobile scan, plan, execution, validation, job lookup, cancellation, and Runner routing. Use for ELMOS frontend worker/API changes or client modernization jobs.
---

# Frontend Client Engine Contract

## Workflow

1. Require tenant, immutable Snapshot, Workspace reference, idempotency key, engine/policy version, budget, and requested operation.
2. Call `/engine/v1/capabilities`; route Web Legacy, Modern Web, Browser Matrix, Desktop Windows/macOS, Android, or iOS work only to an approved matching Runner.
3. Run static discovery without installing packages, importing customer modules, starting servers, or executing package scripts.
4. Submit execution and dynamic validation only after Workspace, image digest, network, secret, browser/device, and cleanup policies are approved.
5. Store content-addressed artifacts as unified Evidence and keep job lookup tenant-scoped.

## Fail-closed rules

- Return `FAILED`, empty `evidenceRefs`, `configured=false`, `executed=false`, and `customerCodeExecuted=false` when a required Runner is unavailable.
- Return conflict when an idempotency key is reused with changed input or a terminal job is cancelled.
- Never use customer login credentials, persist browser cookies, sign production clients, publish stores, accept visual changes, or close accessibility findings.

## Output

Emit the shared Engine response plus `elmos.frontend-client-evidence.v1` extensions. Distinguish static analysis, customer-code execution, and independent validation in every result.
