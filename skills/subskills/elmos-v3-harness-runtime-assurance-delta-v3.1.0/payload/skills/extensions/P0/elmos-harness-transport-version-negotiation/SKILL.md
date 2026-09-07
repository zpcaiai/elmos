---
name: elmos-harness-transport-version-negotiation
description: Provider transport、history、typed result、schema dialect、mode 与版本差异通过能力协商和版本隔离层处理。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Harness Transport, Version and Capability Negotiation

**Skill ID:** `ELMOS-V3D-009`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Provider transport、history、typed result、schema dialect、mode 与版本差异通过能力协商和版本隔离层处理。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#40787`
- `openai/codex#40775`
- `openai/codex#40737`
- `deepseek-harness-v0.1.2-alpha.1`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- ProtocolHandshake
- CapabilityMatrix
- VersionMapper
- TransportAuthenticator
- CompatibilityGate

## Non-negotiable invariants

- canonical Elmos types are stable across upstream renames
- capability negotiation result is immutable for a connection epoch
- history pagination and consistency are explicit protocol properties
- transport authentication is separate from execution authority

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

- adapter negotiates transport, auth, history, typed result, schema dialect and consistency semantics
- unsupported required capability fails closed before execution
- upstream type names and enums never escape the adapter boundary
- DeepSeek ApiProxy is not used for alpha.1 and later Remote-gateway profiles
- Codex main/alpha features are not advertised by the stable 0.150.1 profile

## Threats specifically closed

- adapter assumes a fixed JSON shape
- old ApiProxy path silently used
- Code/PTC enum mismatch
- stable adapter invokes main-only lifecycle hook

## Observability

- `elmos_protocol_negotiation_total`
- `elmos_adapter_unsupported_capability_total`
- `elmos_transport_auth_failure_total`
- `elmos_adapter_version_mismatch_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
