---
name: elmos-tool-result-interception-commit
description: 把 Tool/MCP 结果从 server-returned 提升为 raw→intercepted→committed→published/model-visible 的耐久生命周期。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Tool Result Interception and Commit Boundary

**Skill ID:** `ELMOS-V3D-001`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K6, K8`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

把 Tool/MCP 结果从 server-returned 提升为 raw→intercepted→committed→published/model-visible 的耐久生命周期。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41202`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- ResultLifecycleCoordinator
- InterceptorChain
- ResultIdentityGuard
- ResultCommitJournal
- ReplayResultProjector

## Non-negotiable invariants

- RESULT_COMMIT occurs at most once for invocation_id + attempt + execution_epoch
- effectiveResult is derived only from rawResult plus ordered, signed interceptor decisions
- event publication and downstream model visibility happen strictly after RESULT_COMMIT
- interceptors may replace content/status but not call_id, authority_snapshot_id, environment_id or execution_plan_hash

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

- rawResult and effectiveResult are both content-addressed and revision-bound
- call identity, authority, environment and originating plan cannot be silently mutated
- completion event and model input consume the same committed result
- cancel, timeout, interceptor failure and error replacement have deterministic terminal semantics
- replay reproduces the committed effective result without re-running non-replay-safe interceptors

## Threats specifically closed

- audit ambiguity between raw and rewritten output
- plugin hides a tool error
- duplicate commit after retry
- replay re-executes external side effects

## Observability

- `elmos_tool_result_commit_latency_seconds`
- `elmos_tool_result_mutation_total`
- `elmos_tool_result_commit_conflict_total`
- `elmos_tool_result_replay_mismatch_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
