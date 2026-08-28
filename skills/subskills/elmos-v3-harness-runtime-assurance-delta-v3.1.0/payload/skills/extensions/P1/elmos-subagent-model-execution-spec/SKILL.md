---
name: elmos-subagent-model-execution-spec
description: Subagent 可按任务选择 provider/model/reasoning effort/max output，但环境、权限、预算与 Tool surface 仍受父执行约束。
version: 3.1.0
priority: P1
kind: kernel-extension
routable: false
---

# Subagent Model Execution Specification

**Skill ID:** `ELMOS-V3D-013`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K4, K7`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Subagent 可按任务选择 provider/model/reasoning effort/max output，但环境、权限、预算与 Tool surface 仍受父执行约束。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `deepseek-harness-v0.1.2-alpha.1`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- SubagentSpecCompiler
- ModelPolicyEvaluator
- ParentAuthorityLimiter
- ReasoningBudgetAllocator
- ChildPlanFinalizer

## Non-negotiable invariants

- subagent model inheritance is a default, not a security boundary
- child authority never derives from model capability
- parent ownership and cancellation propagate to child lifecycle
- child results return through typed ingress and result commit

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

- provider, model, reasoning effort and output limit are explicit and policy-validated
- child environment and authority are subsets of parent-authorized resources
- child gets its own finalized step execution plan
- model selection cannot implicitly widen tools, network, secrets or workspace scope
- cost, token and wall-clock budgets are reserved before child activation

## Threats specifically closed

- stronger model receives broader tools
- child bypasses parent budget
- provider switch loses permission semantics
- orphan child writes after parent cancel

## Observability

- `elmos_subagent_model_selection_total`
- `elmos_subagent_authority_widening_blocked_total`
- `elmos_subagent_budget_rejection_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
