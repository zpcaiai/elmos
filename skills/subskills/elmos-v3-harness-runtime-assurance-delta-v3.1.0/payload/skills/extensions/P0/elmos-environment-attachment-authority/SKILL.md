---
name: elmos-environment-attachment-authority
description: Tool/MCP/Executor 的有效权限来自拥有该能力的 Environment/Attachment 快照与上层策略交集，而不是 Thread 全局状态。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Environment and Attachment Owned Authority

**Skill ID:** `ELMOS-V3D-006`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Tool/MCP/Executor 的有效权限来自拥有该能力的 Environment/Attachment 快照与上层策略交集，而不是 Thread 全局状态。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#40728`
- `openai/codex#40771`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- AuthorityOwnerResolver
- EnvironmentAuthoritySnapshot
- AttachmentAuthorityBinder
- EffectivePolicyCalculator
- RuntimeRepublisher

## Non-negotiable invariants

- ToolInvocation→EnvironmentRef→AuthoritySnapshot→EffectivePolicy is mandatory
- effective authority equals owner authority intersected with parent and global policy
- thread defaults are fallback inputs only when an explicit contract permits them
- authority snapshot identity is included in plan, journal, artifacts and certificate

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

- every invocation resolves an explicit authority owner and immutable profile version
- unresolved owner authority rejects tool call and elicitation
- runtime refresh preserves per-server owner authority
- sandbox execution uses the actual owning TurnEnvironment settings
- authority can only stay equal or narrow across agent switch, resume and refresh

## Threats specifically closed

- MCP inherits root thread authority
- refresh republishes server with broader profile
- tool executes in different environment than advertised
- missing attachment falls back to host

## Observability

- `elmos_authority_owner_resolution_failure_total`
- `elmos_authority_widening_blocked_total`
- `elmos_runtime_authority_republish_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
