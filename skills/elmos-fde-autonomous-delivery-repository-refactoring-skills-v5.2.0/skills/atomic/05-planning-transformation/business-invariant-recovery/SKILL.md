---
name: business-invariant-recovery
description: Recover and approve behavioral, data, security, compatibility, performance, and operational invariants that transformations must preserve or intentionally change.
---

# Mission

Recover and approve behavioral, data, security, compatibility, performance, and operational invariants that transformations must preserve or intentionally change.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- recover invariants
- behavior contract
- characterization
- preserve business rules

## Do not use when

- assume existing behavior is correct
- approve business rule without owner

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Select critical user journeys, data, interfaces, state machines, and side effects.
2. Mine candidate invariants from all available evidence sources.
3. Generate positive, negative, boundary, and historical counterexamples.
4. Review conflicts with business, security, data, and operations owners.
5. Encode approved invariants into the registry and verification harness.
6. Create unknown and risk-waiver records for unresolved properties.

## Required outputs

- invariant registry
- behavior classification
- executable oracles
- approval records
- unresolved property register

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

- `business-capability-code-mapping`
- `root-cause-risk-prioritization`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
