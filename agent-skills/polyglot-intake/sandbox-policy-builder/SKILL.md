---
name: sandbox-policy-builder
description: Build a default-deny, rootless, resource-bounded policy for executing unknown repositories through the ELMOS workspace service.
---

# Sandbox Policy Builder

## Default policy

- Network disabled; dependency access requires an explicit allowlist and expiring policy.
- Read-only snapshot/root, separate writable workspace.
- Two CPUs, 4096 MiB memory, 256 processes, 1200-second timeout.
- No secrets by default, no privilege, no host Docker socket, no Docker-in-Docker.
- Package lifecycle scripts disabled by default.

## Workflow

1. Select only an approved digest-pinned image matching the Build Model.
2. Mount snapshot read-only and create a disposable writable volume.
3. Translate network needs into explicit proxy allowlist policy; never enable unrestricted egress.
4. Attach CPU, memory, PID, disk and wall-clock limits.
5. Capture argv, redacted stdout/stderr, exit code, timing and artifact refs.
6. Kill the process tree at timeout, revoke secret leases, seal evidence, and destroy the workspace idempotently.

## Hard boundaries

Never use privileged containers, host home mounts, host Docker socket, host SSH credentials or unbounded public network access. Missing enforcement capabilities block execution.

## Acceptance

Policy output is machine-readable and fail-closed; the workspace service rejects any request that weakens a non-negotiable boundary.
