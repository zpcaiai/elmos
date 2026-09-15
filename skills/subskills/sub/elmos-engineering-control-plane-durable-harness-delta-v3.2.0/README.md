# Elmos Engineering Control Plane & Durable Harness Delta v3.2.0

> Pure incremental Skills Package for **Elmos Proof-Driven Agentic Harness / Repository Semantic Compiler v3.1.x**.
>
> Goal: turn the Harness core from `Agent + Tools + Session` into a production-grade execution model:
>
> **`Execution = Identity + Ownership + TypedContext + Timeline + Artifacts + Policy + Lifecycle + Effects`**

## Why this delta exists

v3.1.0 already established Result Interception/Commit, per-step model-specific ExecutionPlan, lossless PermissionProfile replay, invocation-scoped CapabilityLease, host-minted VerifiedSecurityContext, environment-owned authority, remote-executor fencing, workspace ownership/lease, transport/version/capability negotiation, signed Skill provenance, durable plugin events, typed external ingress and Subagent ExecutionSpec.

v3.2.0 absorbs the next Harness-generation changes and the useful OpenClaw-style engineering-control-plane ideas without coupling Elmos to any one upstream harness.

## P0 contract deltas

1. `RuntimeOwner` and parent-authoritative recovery.
2. Nonterminal `SUSPENDED / HANDOFF_READY` and two-phase handoff.
3. Durable `ExecutionTimeline + TypedArtifactStore + Projection`.
4. Typed `ContextEnvelope` with provenance and propagation semantics.
5. Unified `ExecutionSource + lineage`, separate from lifecycle ownership.
6. `CapabilityInventory` separated from side-effect-free `RuntimeConnectionState` observation.
7. `EffectivePolicy = intersection(Tenant, Harness, Environment, Tool)` with monotonic hard-deny.
8. Fail-closed runtime capability / approval-mode / policy-mapping negotiation.
9. Effect-level `ApprovalActionKind`, not only ToolCall-level approval.
10. `InterruptLifecycle` with durable transcript barrier before abort/suspend.
11. Typed Tool/Plugin lifecycle provenance (`source/phase/blocking/control_effect/cancellation_scope/environment`).
12. `ResultFence + ReconcileTransaction` before publication.
13. Release evidence state model `PASS | FAIL | WAIVED | PENDING` and exact artifact verification.
14. `CertifiedReleaseManifest` binds code, policy, skills, runner, dependencies, evidence and published artifact digests.
15. `MonotonicAuthorityNarrowing`: downstream Runtime/Worker can only preserve or narrow authority.
16. Repository checkpoint path-kind semantics for file↔directory transformations.

## P1 deltas

- Prepared worker pools and project snapshots keyed by `EnvironmentFingerprint`.
- Peer→Agent binding for MCP/ACP/A2A multi-tenant routing.
- PublicationBroker / DeploymentBroker authority separation.
- Internal session inheritance allowlists for reviewer/verifier/guardian roles.
- Capability-class abstraction for computer/browser/network runtimes.
- Engineering observer signals for stuck loops, stale evidence and runtime drift.

## Non-goals / honesty boundary

This package is an implementation specification + executable reference kernel. It does **not** claim that real Codex/Claude/Gemini/OpenClaw, OPA, PostgreSQL, Temporal, remote workers, customer repositories or production environments have been certified merely because this archive validates locally.

It intentionally remains a delta: no new top-level routable Skill is introduced and existing K1–K8 ownership remains canonical.

## Quick validation

```bash
python3 scripts/validate_package.py
PYTHONPATH=reference/src python3 -m unittest discover -s reference/tests -v
```

## Install Codex / Antigravity workflow Skills

```bash
python3 scripts/install_skills.py --repo /absolute/path/to/elmos --agent codex --apply
# or
python3 scripts/install_skills.py --repo /absolute/path/to/elmos --agent antigravity --apply
# or both
python3 scripts/install_skills.py --repo /absolute/path/to/elmos --agent both --apply
```

Without `--apply` the installer is a dry run.
