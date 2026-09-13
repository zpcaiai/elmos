---
name: portfolio-multi-repository-governance
description: Govern architecture, risk, dependencies, transformation waves, evidence, and investment across large multi-repository portfolios.
---

# Mission

Govern architecture, risk, dependencies, transformation waves, evidence, and investment across large multi-repository portfolios.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- portfolio assessment
- many repositories
- modernization program
- organization architecture governance

## Do not use when

- compare teams by raw finding count
- apply one migration recipe to unsupported repos

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Ingest repository-level snapshots, findings, support profiles, plans, and evidence.
2. Resolve cross-repository dependency and ownership graph.
3. Cluster common patterns and incompatible exceptions.
4. Score and sequence modernization waves under constraints.
5. Track program-level value, risk, cost, evidence, and adoption.
6. Publish portfolio decisions while preserving drill-down provenance.

## Required outputs

- portfolio graph
- modernization wave plan
- systemic risk map
- capacity and cost plan
- program dashboard model

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

- `reusable-recipe-skill-learning`
- `support-profile-and-unknown-register`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
