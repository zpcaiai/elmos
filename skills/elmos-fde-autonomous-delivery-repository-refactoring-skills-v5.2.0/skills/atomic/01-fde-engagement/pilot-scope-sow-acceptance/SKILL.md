---
name: pilot-scope-sow-acceptance
description: Convert ambiguous opportunities into bounded PoC, pilot, or production scopes with SOW, acceptance criteria, dependencies, and stop conditions.
---

# Mission

Convert ambiguous opportunities into bounded PoC, pilot, or production scopes with SOW, acceptance criteria, dependencies, and stop conditions.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- SOW
- pilot scope
- acceptance criteria
- project charter
- scope control

## Do not use when

- unbounded build everything request
- production approval without evidence

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Choose the smallest end-to-end workflow that can prove value safely.
2. Declare repositories, environments, users, data, integrations, and side effects in scope.
3. Write functional, non-functional, security, adoption, and evidence acceptance criteria.
4. Map customer and Elmos responsibilities and access prerequisites.
5. Define milestones, review gates, change-control policy, and stop conditions.
6. Obtain explicit approval before implementation starts.

## Required outputs

- SOW
- scope baseline
- acceptance contract
- milestone plan
- approval packet

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

- `stakeholder-workflow-discovery`
- `business-baseline-roi`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
