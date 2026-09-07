---
name: elmos-invocation-scoped-capability-lease
description: Host-owned filesystem、sandbox、secret、executor、emitter 等能力以 invocation 借用租约暴露，调用结束或取消立即吊销。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Invocation-Scoped Capability Lease

**Skill ID:** `ELMOS-V3D-004`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Host-owned filesystem、sandbox、secret、executor、emitter 等能力以 invocation 借用租约暴露，调用结束或取消立即吊销。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41020`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- CapabilityLeaseBroker
- BorrowedHandle
- LeaseRevocationCoordinator
- UseAfterInvocationGuard

## Non-negotiable invariants

- possession of an object reference is not durable authority
- leases are non-transferable unless a typed delegation contract is accepted by the Host
- revocation is monotonic
- child execution authority is always a subset of the parent effective authority

## Inputs

- exact Goal/Run/Execution Epoch and Revision Set;
- originating Step ExecutionPlan hash;
- Environment/Attachment owner and PermissionProfile revision;
- tenant-scoped policy bundle and cost budget;
- typed artifacts or lifecycle events defined by this extension.

## Outputs

- versioned contract object validated by the matching Delta schema;
- content-addressed evidence with complete producer and mutation provenance;
- typed status that distinguishes success, refusal, unsupported, unknown and counterexample;
- affected Proof Obligations and independent certification inputs.

## Workflow

1. Validate tenant, exact revisions, ownership, lease generation and base v3 activation.
2. Resolve the canonical owner Kernel and load the frozen per-step execution context.
3. Reject missing, lossy, stale, unregistered or caller-forged security semantics.
4. Execute deterministic lifecycle transitions and atomically append journal/outbox state.
5. Run positive, negative, cancellation, replay, replacement and recovery verification.
6. Emit immutable evidence; any external side effect remains unsettled until reconciled.
7. Hand the result to the owning K1/K4/K5/K6/K7/K8 workflow; never self-certify.

## Hard gates

- capability lease is bound to invocation, environment, authority snapshot and execution epoch
- returned future cannot outlive the invocation lease
- cancel, timeout, turn abort and executor replacement revoke all borrowed capabilities
- plugins cannot persist or deserialize a live host capability
- use-after-revoke is rejected and audited

## Threats specifically closed

- plugin caches sandbox handle
- async task continues after cancel
- subagent retains parent secret handle
- stale remote executor uses old filesystem capability

## Observability

- `elmos_capability_lease_active`
- `elmos_capability_use_after_revoke_total`
- `elmos_capability_revocation_latency_seconds`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
