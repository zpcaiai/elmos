---
name: elmos-registered-durable-plugin-events
description: 插件只能写入注册、版本化、可升级的 durable event；required state 与 optional observation 具有不同恢复语义。
version: 3.1.0
priority: P1
kind: kernel-extension
routable: false
---

# Registered Durable Plugin Events

**Skill ID:** `ELMOS-V3D-011`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K8`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

插件只能写入注册、版本化、可升级的 durable event；required state 与 optional observation 具有不同恢复语义。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `deepseek-harness-discussion-4815-ecosystem-signal`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- DurableEventRegistry
- EventSchemaValidator
- EventUpgrader
- ProjectionRegistry
- UnknownEventRecoveryGate

## Non-negotiable invariants

- plugins cannot append arbitrary unregistered string event types
- required state is never treated as ignorable observation
- event schema upgrades are deterministic and content-addressed
- unknown required event prevents authoritative resume

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

- every durable plugin event has owner, schema version, semantics, validator, upgrader and projections
- required-state unknown events fail closed on replay
- optional observations may be skipped only with an explicit compatibility rule
- plugin uninstall and downgrade run a preflight recovery analysis
- fork and migration preserve event causality and schema lineage

## Threats specifically closed

- plugin removal makes session unreadable
- unknown event silently skipped
- event type collision
- downgrade misprojects newer required state

## Observability

- `elmos_plugin_event_validation_failure_total`
- `elmos_unknown_required_event_total`
- `elmos_event_upgrade_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
