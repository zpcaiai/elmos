---
name: elmos-workspace-ownership-lease
description: Workspace 不再只是 cwd；它具有 owner execution、generation、repository/base revision 和可转移生命周期。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Workspace Ownership and Lease

**Skill ID:** `ELMOS-V3D-008`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K5`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Workspace 不再只是 cwd；它具有 owner execution、generation、repository/base revision 和可转移生命周期。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#40716`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- WorkspaceOwnerRegistry
- NoClobberBinder
- WorkspaceLease
- TakeoverCoordinator
- SubagentScopeAllocator

## Non-negotiable invariants

- workspace_id identifies an owned resource, not a path string
- one writable generation has at most one authoritative owner
- parent and subagent write scopes are disjoint unless an explicit coordination protocol is active
- artifact lineage records workspace owner and base revision

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

- workspace ownership is acquired atomically with no-clobber semantics
- repeat binding by the same owner is idempotent
- conflicting owner, primary checkout, nested checkout and unmanaged checkout are rejected
- resume validates owner and generation before write access
- handoff and crash takeover are explicit, fenced transitions

## Threats specifically closed

- two executions modify one checkout
- stale owner commits after takeover
- subagent writes parent worktree
- path alias bypasses ownership registry

## Observability

- `elmos_workspace_lease_active`
- `elmos_workspace_owner_conflict_total`
- `elmos_workspace_stale_owner_rejected_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
