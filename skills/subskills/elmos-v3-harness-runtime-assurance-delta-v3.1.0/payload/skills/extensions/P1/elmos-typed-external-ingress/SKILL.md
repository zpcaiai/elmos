---
name: elmos-typed-external-ingress
description: UserInput、ToolResultIngress、ExternalEventIngress、ApprovalInput 和 ControlInput 是不同的一等 Turn/Steering 输入。
version: 3.1.0
priority: P1
kind: kernel-extension
routable: false
---

# Typed Tool Result and External Event Ingress

**Skill ID:** `ELMOS-V3D-012`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K1`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

UserInput、ToolResultIngress、ExternalEventIngress、ApprovalInput 和 ControlInput 是不同的一等 Turn/Steering 输入。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41002`
- `openai/codex#40737`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- IngressRouter
- CausalityBinder
- DeduplicationLedger
- TypedContentNormalizer
- ResumeIngressProjector

## Non-negotiable invariants

- one ingress envelope has one semantic kind
- authoritative external result must reference a valid pending or reconciled origin
- content type and security classification survive adapter conversion
- deduplication key is scoped by tenant, execution and producer

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

- external result is never rewritten as a fake user message
- producer, originating call, event, causation and correlation identities are persisted
- duplicate delivery is idempotently rejected or reconciled
- typed text/media/encrypted/unknown content is preserved without stringify loss
- resume and paginated history reproduce ingress causality

## Threats specifically closed

- CI callback impersonates user
- duplicate callback runs repair twice
- media output lost by JSON stringify
- stale subagent result steers new epoch

## Observability

- `elmos_ingress_received_total`
- `elmos_ingress_duplicate_total`
- `elmos_ingress_causality_failure_total`
- `elmos_typed_content_loss_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
