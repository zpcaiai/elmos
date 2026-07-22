---
name: build-secret-injector
description: Build or review short-lived build-secret leasing, tmpfs/file injection, log redaction, and revocation in ELMOS sandboxes. Use for Maven/Gradle credentials, SCM tokens, secret providers, or command-output handling.
---

# Build Secret Injector

Lease the smallest secret for the shortest operation, inject it outside durable layers, redact it from output, and revoke it independently of job success.

## Required workflow

1. Authorize the workspace, repository, operation, and requested secret type.
2. Lease a short-lived value through a secret-provider port and persist metadata only.
3. Materialize it in a workspace tmpfs file with mode `0400`, owned by the sandbox uid; prefer tool-specific settings files over environment variables.
4. Redact exact values and common credential/header forms from streamed output before storage.
5. Remove the file, revoke the lease, and zero local buffers in a `finally` path.

## Non-negotiable boundaries

- Never place secrets in image layers, Docker build args, command argv, source volumes, durable artifacts, databases, or logs.
- Never share a lease between workspaces or extend it silently.
- Failure to revoke is a security event and requires retry/reaper handling.
- Redaction is defense in depth; injection design must avoid exposure first.

## Acceptance checks

- Sentinel tests inspect argv, environment metadata, logs, artifacts, and database rows for absence.
- File permissions, tmpfs placement, expiry, cleanup, and buffer clearing are tested.
- Artifact upload failure still triggers secret removal and revocation.
- Lease status is auditable without revealing a value or stable fingerprint.

