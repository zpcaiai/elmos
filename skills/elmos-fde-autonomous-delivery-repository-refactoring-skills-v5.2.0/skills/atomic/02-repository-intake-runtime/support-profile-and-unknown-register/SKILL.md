---
name: support-profile-and-unknown-register
description: Declare technology support depth, analysis coverage, evidence freshness, unsupported areas, and unknowns without overstating completeness.
---

# Mission

Declare technology support depth, analysis coverage, evidence freshness, unsupported areas, and unknowns without overstating completeness.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- support matrix
- unknown register
- coverage statement
- can you analyze this project

## Do not use when

- claim all issues found
- hide unsupported assets
- convert uncertainty into low-severity finding

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Load asset inventory and available analyzers, adapters, toolchains, and fixtures.
2. Compute support depth and coverage for each technology and system surface.
3. Create unknown records with owner, impact, resolution path, and release effect.
4. Assess evidence age and RevisionSet compatibility.
5. Evaluate release blockers under policy.
6. Publish the support profile and completeness statement.

## Required outputs

- support profile
- coverage matrix
- unknown register
- completion blockers
- honest completeness statement

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

- `asset-inventory-and-classification`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
