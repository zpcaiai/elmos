---
name: e0-e3-readiness-and-evidence-bundle
description: Assemble and independently judge E0-E3 capability readiness from exact revisions, environments, tools, claims, counterexamples, waivers, and evidence.
---

# Mission

Assemble and independently judge E0-E3 capability readiness from exact revisions, environments, tools, claims, counterexamples, waivers, and evidence.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- E0 E3 readiness
- evidence bundle
- production readiness packet
- certification preparation

## Do not use when

- issue E4 or E5 certificate
- approve stale evidence
- let adapter certify itself

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Freeze the candidate RevisionSet and acceptance scope.
2. Collect claims, evidence, counterexamples, waivers, unknowns, and provenance.
3. Check coverage, freshness, independence, tool pins, environment identity, and side effects.
4. Evaluate E0, E1, E2, and E3 gates separately.
5. Route missing or contradictory evidence to remediation rather than averaging it away.
6. Seal the evidence bundle and record the independent readiness decision.

## Required outputs

- E0-E3 evidence bundle
- gate matrix
- independent readiness decision
- blocker list
- companion-package handoff

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

- `characterization-differential-mutation-verification`
- `security-privacy-supply-chain-audit`
- `performance-reliability-observability-audit`
- `test-ci-cd-developer-experience-audit`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
