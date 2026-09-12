---
name: cost-finops-sustainability-audit
description: Audit unit economics, token and compute usage, cloud resources, storage, network, licenses, idle capacity, and sustainability signals.
---

# Mission

Audit unit economics, token and compute usage, cloud resources, storage, network, licenses, idle capacity, and sustainability signals.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- FinOps
- cost audit
- token cost
- cloud waste
- unit economics

## Do not use when

- personal finance
- guaranteed savings
- optimize cost by weakening required controls

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Collect cost and usage data with exact time, tenant, workflow, and version identity.
2. Normalize unit cost and allocate shared resources using declared rules.
3. Relate spend to acceptance progress, evidence value, and business outcomes.
4. Identify waste, capacity, routing, caching, and scheduling opportunities.
5. Simulate conservative savings and quality impact.
6. Publish cost findings and controlled optimization experiments.

## Required outputs

- unit economics
- cost findings
- machine wall-clock report
- optimization experiments
- budget alerts

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

- `status-risk-decision-communications`
- `performance-reliability-observability-audit`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
