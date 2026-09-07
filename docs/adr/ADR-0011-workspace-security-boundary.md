# ADR-0011: Rootless workspace security boundary

Status: Accepted

## Decision

Only the workspace service may access a proven rootless Docker API. Workspaces use approved image digests, non-root uid/gid, read-only root filesystems, dropped capabilities, no-new-privileges, bounded CPU/memory/pids/disk/time, explicit mounts, argv execution, and a per-workspace internal network.

## Consequences

The control plane has no Docker dependency or socket. Source-level configuration tests do not satisfy the live rootless isolation gate.
