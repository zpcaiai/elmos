---
name: elmos-host-minted-security-context
description: CallerMetadata 不可信；身份、租户、许可证和 entitlement 只能由 Harness/Policy Broker 验证并签发。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Host-Minted Verified Security Context

**Skill ID:** `ELMOS-V3D-005`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K8`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

CallerMetadata 不可信；身份、租户、许可证和 entitlement 只能由 Harness/Policy Broker 验证并签发。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41005`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- CallerMetadataSanitizer
- SecurityContextBroker
- EligibilityEvaluator
- ContextBindingSigner
- AccountRaceGuard

## Non-negotiable invariants

- CallerMetadata, VerifiedSecurityContext and ExecutionAuthority are distinct types
- only the Host/Policy Broker can create a verified context
- verified context is invocation-scoped and non-forwardable by default
- execution authority is the intersection of verified context, owner authority and policy decision

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

- caller-supplied verified context is stripped before policy evaluation
- Host minting binds plugin, tool, account, tenant, environment, invocation and policy version
- eligibility failures and account races yield UNKNOWN or DENY, never optimistic grant
- security-context lookup time is charged to the invocation timeout budget
- remote, mutable, undeclared or argument-bearing privileged paths are denied unless explicitly contracted

## Threats specifically closed

- caller forges tenant entitlement
- account changes during verification
- remote MCP receives local-only grant
- adapter mixes untrusted and verified JSON fields

## Observability

- `elmos_verified_context_mint_total`
- `elmos_caller_security_metadata_stripped_total`
- `elmos_security_context_unknown_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
