---
name: elmos-secure-sandbox-runtime
description: Execute untrusted repositories, build scripts, generated code, and plugins
  in tiered, policy-driven isolation with network and secret controls.
version: 1.0.0
priority: P0
phase: G4
dependencies:
- elmos-identity-tenant-security
- elmos-runner-scheduler-execution
- elmos-reproducible-toolchain
---

# Secure Sandbox Runtime and Capability Isolation

## Objective

Provide enforceable per-task isolation whose strength matches source sensitivity and execution risk.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Secure Sandbox Runtime and Capability Isolation** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-identity-tenant-security`
- `elmos-runner-scheduler-execution`
- `elmos-reproducible-toolchain`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Default deny network, host mounts, devices, privilege escalation, and undeclared capabilities.
- Every task receives a fresh writable workspace and read-only toolchain.
- Secrets are short-lived, scoped, redacted, and revoked after execution.
- Snapshots may accelerate startup but never replace workflow checkpoints or CAS.

## Required inputs

- Action and sandbox policy.
- Runner capabilities and security tier.
- Workspace/toolchain manifests.
- Secret and egress references.

## Required outputs

- `Versioned sandbox-policy schema.`
- `Rootless OCI baseline.`
- `gVisor/microVM strong-isolation adapters.`
- `Egress proxy and capability controls.`
- `WASM plugin sandbox.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

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

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Attempt host mount, Docker socket, metadata endpoint, private network, path escape, fork bomb, and device access.
- [ ] Run cross-tenant residual disk/memory tests.
- [ ] Inject secrets and prove they are absent from logs, cache, artifact, trace, and evidence.
- [ ] Cancel/timeout nested processes and verify complete cleanup.
- [ ] Crash malicious WASM plugins without affecting the runner.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Untrusted tasks have no implicit network or host access.
- [ ] Every execution is bound to an auditable policy and compatible tier.
- [ ] Secrets and tenant data do not survive terminal cleanup.
- [ ] Escape and cross-tenant regression suites are release gates.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
