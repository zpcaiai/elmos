---
name: docker-workspace-provisioner
description: Build or review the isolated ELMOS Docker workspace service and lifecycle. Use for Docker API adapters, workspace creation, command execution, resource constraints, mount rules, or control-plane separation.
---

# Docker Workspace Provisioner

Provision customer-code workspaces only through the dedicated workspace service and Docker API. The control plane must not own a Docker socket or execute commands.

## Required workflow

1. Refuse startup or provisioning when rootless Docker cannot be proven.
2. Resolve only an approved image digest; never execute a mutable tag.
3. Create per-workspace volumes and an internal network with no external connectivity by default.
4. Create the container as a fixed non-root uid/gid with read-only root filesystem, all capabilities dropped, `no-new-privileges`, bounded pids, CPU, memory, and memory-swap equal to memory.
5. Mount snapshot input read-only and writable output/work paths explicitly.
6. Execute an argv array with a validated working directory; never invoke a shell string.
7. Capture bounded stdout/stderr artifacts and enforce wall-clock termination.

## Non-negotiable boundaries

- No privileged containers, host PID/network, Docker socket mount, host root mount, or unbounded resource field.
- Workspace ids, volume names, and labels are server-generated and validated.
- A container or volume owned by another tenant/workspace must never be reused.
- Every provision/exec/destroy call is idempotent by request key.

## Acceptance checks

- Specification tests assert every security option and limit.
- Architecture tests prove the control plane has no Docker client dependency.
- Integration tests against rootless Docker verify uid, read-only root, resource limits, and default network denial.
- Missing Docker evidence leaves the live-runtime gate incomplete; do not simulate success.

