---
name: elmos-executor-generation-fencing
description: 区分同一 Executor 重连与计划替换；所有远程 RPC、进程、回调和 Artifact commit 携带 generation/epoch fencing。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Remote Executor Generation and Fencing

**Skill ID:** `ELMOS-V3D-007`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

区分同一 Executor 重连与计划替换；所有远程 RPC、进程、回调和 Artifact commit 携带 generation/epoch fencing。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#40710`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- ExecutorConnectionStateMachine
- GenerationIssuer
- LateResultFence
- OutstandingWorkReconciler
- LiveProbeGate

## Non-negotiable invariants

- authoritative remote commit requires matching executor_generation and connection_epoch
- generation only increases for a logical environment
- retired generations cannot publish state even if cancellation was lost
- replacement preserves logical environment identity but not stale capabilities

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

- ReconnectSameExecutor and ReplaceExecutor are distinct transitions
- replacement retires old sessions and connection attempts before activation
- old-generation RPC, callback, process state and artifact commits are rejected
- new executor passes a live status probe before becoming authoritative
- outstanding side effects are reconciled rather than blindly replayed

## Threats specifically closed

- late RPC overwrites new state
- spot recovery duplicates build/upload
- old session replays outstanding work
- connection race activates two executors

## Observability

- `elmos_executor_generation`
- `elmos_stale_executor_result_rejected_total`
- `elmos_executor_replacement_total`
- `elmos_executor_live_probe_failure_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
