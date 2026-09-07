---
name: elmos-step-finalized-execution-plan
description: 每个模型采样 Step 在模型选择后冻结独立的模型快照、Tool surface、模式、环境、权限与执行能力。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Per-Model Step Finalized Execution Plan

**Skill ID:** `ELMOS-V3D-002`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K4`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

每个模型采样 Step 在模型选择后冻结独立的模型快照、Tool surface、模式、环境、权限与执行能力。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41195`
- `openai/codex#36357`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- CandidatePlanBuilder
- ExecutionPlanFinalizer
- ActivePlanStore
- FallbackIsolationGuard
- PlanHashVerifier

## Non-negotiable invariants

- Step = modelSnapshot + environmentSnapshot + authoritySnapshot + finalizedCapabilities + lifecycle + committedEffects
- candidate plan namespaces are isolated until atomic activation
- one step has one authoritative execution_plan_hash
- capability exposure is never inferred from a session-global ToolRegistry

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

- active plan is finalized from the exact selected model snapshot
- fallback or candidate planning cannot mutate active tool metadata
- advertised tool specifications and executed handlers share one plan hash
- model switch, fallback, resume or environment refresh triggers explicit re-plan
- tool call dispatch uses the originating step plan even when the call outlives sampling

## Threats specifically closed

- fallback planning contaminates current request
- model sees tool unavailable to executor
- late call runs under newly selected model plan
- subagent inherits wrong tool surface

## Observability

- `elmos_execution_plan_finalize_seconds`
- `elmos_candidate_plan_isolation_violation_total`
- `elmos_plan_dispatch_hash_mismatch_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
