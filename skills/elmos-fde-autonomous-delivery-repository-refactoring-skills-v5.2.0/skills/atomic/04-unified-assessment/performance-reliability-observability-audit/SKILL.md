---
name: performance-reliability-observability-audit
description: Audit latency, throughput, capacity, algorithms, resources, resilience, recovery, observability, SLOs, and operational failure behavior.
---

# Mission

Audit latency, throughput, capacity, algorithms, resources, resilience, recovery, observability, SLOs, and operational failure behavior.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- performance audit
- reliability audit
- capacity
- SLO
- observability gaps

## Do not use when

- benchmark on non-representative data without caveat
- optimize before measuring

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Identify critical journeys, workload envelopes, SLOs, and failure budgets.
2. Inspect code and configuration for likely bottlenecks and resilience gaps.
3. Collect profiles, query plans, telemetry, and resource curves in the runtime lab.
4. Run load, soak, stress, and approved fault tests at staged scale.
5. Correlate bottlenecks and operational symptoms to root causes.
6. Publish findings, capacity model, and observability remediation plan.

## Required outputs

- performance findings
- reliability findings
- capacity model
- SLO and observability gap map
- cost impact

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

- `issue-ontology-and-finding-normalization`
- `runtime-observation-and-traffic-capture`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
