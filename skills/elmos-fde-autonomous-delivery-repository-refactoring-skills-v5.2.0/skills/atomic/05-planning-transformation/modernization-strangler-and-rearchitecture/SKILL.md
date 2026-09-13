---
name: modernization-strangler-and-rearchitecture
description: Execute phased framework, platform, architecture, and monolith modernization through compatibility layers, strangler patterns, and reversible cutovers.
---

# Mission

Execute phased framework, platform, architecture, and monolith modernization through compatibility layers, strangler patterns, and reversible cutovers.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- modernize legacy system
- strangler migration
- framework upgrade
- monolith decomposition

## Do not use when

- big-bang rewrite by default
- remove legacy path before equivalence evidence

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Select a bounded capability and document current and target contracts.
2. Introduce characterization, compatibility, telemetry, and routing seams.
3. Implement the new path behind a reversible switch.
4. Run replay, shadow, or dual execution and reconcile differences.
5. Increase traffic or ownership in controlled stages with rollback triggers.
6. Retire the old path and update architecture knowledge only after approval.

## Required outputs

- transition architecture
- modernized capability
- compatibility layer
- cutover evidence
- legacy retirement plan

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

- `proof-guided-atomic-refactor-execution`
- `target-architecture-alternatives-and-adr`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
