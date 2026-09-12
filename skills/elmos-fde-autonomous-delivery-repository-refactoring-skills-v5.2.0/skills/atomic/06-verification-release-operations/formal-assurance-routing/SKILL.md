---
name: formal-assurance-routing
description: Route high-risk properties to appropriate formal, symbolic, model-checking, contract, or translation-validation methods with explicit trusted computing base.
---

# Mission

Route high-risk properties to appropriate formal, symbolic, model-checking, contract, or translation-validation methods with explicit trusted computing base.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- formal verification
- TLA+
- SMT
- model checking
- prove invariant

## Do not use when

- formalize the entire repository by default
- claim proof without checking tool output
- hide modeling assumptions

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Classify the property and failure consequence.
2. Choose executable contract, symbolic execution, SMT, model checking, theorem proving, or translation validation.
3. Define the model boundary, assumptions, and source-to-model traceability.
4. Generate and independently check the artifact using pinned tools.
5. Interpret counterexamples against implementation and environment evidence.
6. Publish proof scope, result, TCB, residual risk, and invalidation triggers.

## Required outputs

- formal-method selection
- model or proof artifact
- checker evidence
- counterexamples
- TCB and assumption report

## Invariants

- no claim without evidence
- no authority escalation
- all unknowns are explicit
- outputs bind to exact RevisionSet

## Fail closed on

- insufficient evidence
- unsupported technology
- stale RevisionSet
- authority denied
- validation failure
- Material `UNKNOWN`, `UNSUPPORTED`, stale evidence, unresolved critical side effects, or missing approvals.
- Any attempt by this Skill or an Adapter to become the canonical completion authority.

## Authority and side effects

Default deny. Read, workspace-write, external-write, and production-write are separate capabilities. Production writes are prohibited by this capability package. Tool results must be intercepted and checked against the approved plan before commit. Checkpoint before external effects and after each accepted ChangeSet.

## Definition of done

- All checks in `acceptance.yaml` pass with exact revision and environment identity.
- Evidence, counterexamples, unknowns, decisions, cost, and machine wall-clock are recorded.
- An independent verifier returns the result to K8; the producer does not self-approve.
- The maximum standalone claim is E3 capability readiness. E4/E5/P05 require the independent companion package and authorized customer execution.

## Local dependencies

- `business-invariant-recovery`
- `correctness-concurrency-consistency-audit`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
