---
name: elmos-skill-trust-domain-provenance
description: Skill 执行事实与 Skill 授权可信度分离；只有验证后的 trust root、签名、digest 和 install scope 才能成为授权证据。
version: 3.1.0
priority: P0
kind: kernel-extension
routable: false
---

# Skill Trust Domain and Signed Provenance

**Skill ID:** `ELMOS-V3D-010`  
**Release:** `Elmos v3.1.0 delta`  
**Canonical owners:** `K7, K8`  
**Routing:** internal-only; this Skill cannot become an independent control plane.

## Purpose

Skill 执行事实与 Skill 授权可信度分离；只有验证后的 trust root、签名、digest 和 install scope 才能成为授权证据。

This extension refines existing v3 Kernel contracts. It does not create a ninth Kernel, a new business line, or a second source of truth. Invocation must originate from one of the existing 16 routable v3 entrypoints and carry the exact Goal Revision Set, execution epoch, environment/authority snapshot and evidence policy.

## Upstream evidence absorbed

- `openai/codex#41006`

Upstream names and types are evidence, not Elmos public API. Elmos adapters translate them into provider-neutral contracts and report loss explicitly.

## Responsibilities

- SkillProvenanceVerifier
- CanonicalPathGuard
- TrustDomainPolicy
- SignatureVerifier
- InvocationEvidenceRecorder

## Non-negotiable invariants

- skill invocation does not by itself imply authorization
- trust domains USER, ENTERPRISE, MARKETPLACE, REPOSITORY and EPHEMERAL are distinct
- same display name never merges provenance identities
- authorization semantics are explicit and least-privilege

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

- canonical path resolves inside the declared trusted root without symlink escape
- package digest and signature satisfy trust-domain policy
- repository skills cannot impersonate user or enterprise installed skills
- authorization evidence contains verified identity/provenance, not untrusted skill content
- digest drift or package substitution invalidates prior authorization evidence

## Threats specifically closed

- repo forges trusted SKILL.md
- symlink escapes trusted root
- package replaced after approval
- marketplace publisher collision

## Observability

- `elmos_skill_provenance_verified_total`
- `elmos_skill_symlink_escape_blocked_total`
- `elmos_skill_digest_drift_total`

Every signal includes tenant, goal, run, execution epoch, step, invocation, environment, authority profile, workspace/executor generation, adapter/version and evidence lineage when applicable.

## Stop and escalate

Stop with a typed failure when authority cannot be resolved, a mapping is lossy, a required event is unknown, a generation is stale, a commit conflicts, the provider lacks a required capability, or a verifier finds a counterexample. Escalation must include the minimal replay bundle and machine wall-clock/cost impact.

## Definition of done

This extension is locally complete only when all hard gates have immutable evidence and its state is durably committed. Only K8 may incorporate that evidence into `VERIFIED_COMPLETE`.
