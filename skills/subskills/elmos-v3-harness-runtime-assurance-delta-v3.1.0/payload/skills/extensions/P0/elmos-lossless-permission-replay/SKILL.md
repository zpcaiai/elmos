---
name: elmos-lossless-permission-replay
description: Canonical PermissionProfile 是唯一持久权限语义；Provider sandbox enum 只允许精确映射，Lossy/Unsupported 默认拒绝。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Lossless Permission Replay and Adapter Mapping

**Skill ID:** `ELMOS-V3D-003`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K8`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Canonical PermissionProfile 是唯一持久权限语义；Provider sandbox enum 只允许精确映射，Lossy/Unsupported 默认拒绝。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41192`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- CanonicalPermissionStore
- PermissionProjectionAdapter
- ReplayPermissionVerifier
- WorkingDirectoryCompatibilityGuard

## Non-negotiable invariants

- canonical PermissionProfile is provider-neutral and versioned
- adapter projection result is one of EXACT, LOSSY, UNSUPPORTED
- LOSSY and UNSUPPORTED cannot start execution without an explicit, narrower replacement profile
- resume cannot derive security authority from display-oriented legacy fields

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

- serialize→resume→adapter-map preserves permission semantics exactly
- lossy and unsupported projections fail closed
- working-directory changes cannot widen restored filesystem authority
- legacy compatibility fields never overwrite a richer canonical profile
- certificate records the exact permission profile and adapter mapping result

## Threats specifically closed

- permission collapse on resume
- cwd change escapes restored roots
- legacy client echoes coarse sandbox
- adapter silently drops network restrictions

## Observability

- `elmos_permission_projection_total`
- `elmos_permission_lossy_rejected_total`
- `elmos_permission_replay_equivalence_failure_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
