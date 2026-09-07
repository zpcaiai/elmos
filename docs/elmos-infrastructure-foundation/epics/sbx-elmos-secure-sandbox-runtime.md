# Secure Sandbox Runtime and Capability Isolation

- Skill: `elmos-secure-sandbox-runtime`
- Priority: `P0`
- Phase: `G4`
- Dependencies: `elmos-identity-tenant-security`, `elmos-runner-scheduler-execution`, `elmos-reproducible-toolchain`

## Objective

Provide enforceable per-task isolation whose strength matches source sensitivity and execution risk.

## Task groups

### Policy contract

- [ ] `ELMOS-SBX-001` Define tiers S0 trusted native, S1 rootless OCI, S2 gVisor, S3 Firecracker/Kata, and S4 Wasmtime/WASI plugin.
- [ ] `ELMOS-SBX-002` Define filesystem, network, process, device, resource, secret, output, timeout, and audit fields.
- [ ] `ELMOS-SBX-003` Map repository sensitivity, tenant policy, action type, and risk to a minimum tier.
- [ ] `ELMOS-SBX-004` Reject scheduling when no runner can satisfy the required tier.
- [ ] `ELMOS-SBX-005` Version policy decisions and include their digest in action identity.

### Rootless OCI baseline

- [ ] `ELMOS-SBX-006` Run with non-root user, rootless runtime, read-only root filesystem, isolated writable workspace, and minimal capabilities.
- [ ] `ELMOS-SBX-007` Apply seccomp plus AppArmor or SELinux where supported.
- [ ] `ELMOS-SBX-008` Set CPU, memory, disk, PID, file-count, output-size, and wall-clock limits.
- [ ] `ELMOS-SBX-009` Deny Docker socket, host paths, devices, privileged mode, and namespace sharing.
- [ ] `ELMOS-SBX-010` Terminate complete child-process trees on cancel, timeout, or runner loss.
- [ ] `ELMOS-SBX-011` Detect path traversal, symlink escape, fork bomb, and workspace quota abuse.

### Network and egress

- [ ] `ELMOS-SBX-012` Default deny outbound and inbound network.
- [ ] `ELMOS-SBX-013` Route approved outbound traffic through an authenticated egress proxy.
- [ ] `ELMOS-SBX-014` Allowlist domain, resolved IP range, protocol, port, purpose, and expiry.
- [ ] `ELMOS-SBX-015` Deny cloud metadata, loopback escape, private networks, and unapproved DNS resolvers.
- [ ] `ELMOS-SBX-016` Restrict dependency downloads to approved registries/proxies and record destination/bytes.
- [ ] `ELMOS-SBX-017` Apply task and tenant bandwidth budgets with stop or approval behavior.

### Secret handling

- [ ] `ELMOS-SBX-018` Inject secrets through short-lived memory/file mechanisms rather than image layers or durable task records.
- [ ] `ELMOS-SBX-019` Issue least-privilege repository, registry, model, and signing credentials per operation.
- [ ] `ELMOS-SBX-020` Prevent secrets from entering command echo, logs, traces, checkpoints, caches, artifacts, or evidence.
- [ ] `ELMOS-SBX-021` Revoke credentials and erase temporary material on every terminal path.
- [ ] `ELMOS-SBX-022` Scan declared outputs and logs for secret patterns before upload.

### Strong isolation

- [ ] `ELMOS-SBX-023` Integrate gVisor for untrusted generated code and install scripts.
- [ ] `ELMOS-SBX-024` Provide Firecracker or Kata adapter for high-assurance multi-tenant/customer workloads.
- [ ] `ELMOS-SBX-025` Boot microVMs from signed immutable images and isolated kernels.
- [ ] `ELMOS-SBX-026` Use snapshot restore only from tenant-neutral prewarmed state.
- [ ] `ELMOS-SBX-027` Reissue identity and secrets after restore and erase disks/memory between tenants.
- [ ] `ELMOS-SBX-028` Capture runtime/kernel/image provenance in evidence.

### WASM plugins

- [ ] `ELMOS-SBX-029` Define a versioned Wasmtime Component/WASI ABI for rule and evidence plugins.
- [ ] `ELMOS-SBX-030` Grant explicit capabilities for files, clocks, randomness, environment, and network.
- [ ] `ELMOS-SBX-031` Set fuel, memory, output, and time limits.
- [ ] `ELMOS-SBX-032` Require signed plugin packages and compatible interface versions.
- [ ] `ELMOS-SBX-033` Contain plugin trap/crash without crashing the runner.

### Security operations

- [ ] `ELMOS-SBX-034` Record sandbox start, policy, denials, egress, resource termination, and cleanup events.
- [ ] `ELMOS-SBX-035` Quarantine a runner after integrity violations or repeated escape indicators.
- [ ] `ELMOS-SBX-036` Maintain escape, residual-data, metadata-access, secret-leak, and malicious-package regression suites.
- [ ] `ELMOS-SBX-037` Publish runbooks for cleanup failure, suspected compromise, and certificate revocation.

## Validation

- [ ] Attempt host mount, Docker socket, metadata endpoint, private network, path escape, fork bomb, and device access.
- [ ] Run cross-tenant residual disk/memory tests.
- [ ] Inject secrets and prove they are absent from logs, cache, artifact, trace, and evidence.
- [ ] Cancel/timeout nested processes and verify complete cleanup.
- [ ] Crash malicious WASM plugins without affecting the runner.

## Exit gate

- [ ] Untrusted tasks have no implicit network or host access.
- [ ] Every execution is bound to an auditable policy and compatible tier.
- [ ] Secrets and tenant data do not survive terminal cleanup.
- [ ] Escape and cross-tenant regression suites are release gates.
