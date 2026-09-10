---
name: shadow-dual-run-canary-rollback-preparation
description: Prepare shadow, dual-run, canary, feature-flag, reconciliation, rollback, and incident controls for later E4/E5 execution by authorized environments.
---

# Mission

Prepare shadow, dual-run, canary, feature-flag, reconciliation, rollback, and incident controls for later E4/E5 execution by authorized environments.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- canary plan
- shadow traffic
- dual run
- rollback plan
- feature flag rollout

## Do not use when

- perform unapproved production cutover
- claim E4 or E5
- duplicate real side effects during shadow

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Select deployment topology and change blast radius.
2. Design shadow or dual execution with side-effect isolation.
3. Define cohort, metrics, thresholds, duration, escalation, and rollback policy.
4. Generate deployment, observability, reconciliation, and recovery artifacts.
5. Rehearse in representative non-production environments.
6. Package approved production instructions for the independent release authority.

## Required outputs

- rollout plan
- shadow and side-effect isolation plan
- rollback package
- reconciliation plan
- E4/E5 execution handoff

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

- `e0-e3-readiness-and-evidence-bundle`
- `changeset-commit-and-provenance-governance`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
