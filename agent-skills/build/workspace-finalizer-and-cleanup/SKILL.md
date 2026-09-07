---
name: workspace-finalizer-and-cleanup
description: Build or review idempotent ELMOS workspace finalization, artifact sealing, secret revocation, Docker cleanup, retention, and orphan reaping. Use for success, failure, cancellation, timeout, or crash recovery paths.
---

# Workspace Finalizer and Cleanup

Finalize every terminal workspace through one idempotent workflow. Security cleanup must continue even when evidence upload or another cleanup step fails.

## Required workflow

1. Acquire an idempotent finalization claim for the workspace and terminal cause.
2. Stop/kill active execution and prevent new commands.
3. Seal bounded logs/results and attempt artifact upload with checksums.
4. In independent `finally` paths remove injected secrets, revoke leases, detach/remove the container, network, and volumes.
5. Record each cleanup action and failure separately; schedule retry when any mandatory action is incomplete.
6. Run a reaper for expired leases and orphaned resources selected only by immutable ELMOS ownership labels.

## Non-negotiable boundaries

- Repeat calls and Docker `404` results are successful no-ops.
- Never delete unlabeled resources or resources owned by a different workspace/tenant.
- Artifact failure must not block credential revocation or container isolation.
- A workspace is `FINALIZED` only after every mandatory security cleanup action is complete.

## Acceptance checks

- Tests cover normal completion, cancellation, timeout, duplicate finalization, partial failure, and retry.
- Secret revocation is observed even when artifact storage throws.
- Reaper selection requires ownership labels plus expiry and records an audit event.
- Live Docker cleanup remains an explicit environment gate when no daemon is available.
