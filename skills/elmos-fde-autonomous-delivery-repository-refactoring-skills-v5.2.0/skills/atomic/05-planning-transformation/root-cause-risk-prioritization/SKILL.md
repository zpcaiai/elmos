---
name: root-cause-risk-prioritization
description: Cluster findings into root causes and prioritize remediation by business impact, risk reduction, dependency, effort, and evidence confidence.
---

# Mission

Cluster findings into root causes and prioritize remediation by business impact, risk reduction, dependency, effort, and evidence confidence.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- root cause
- prioritize findings
- remediation roadmap
- technical debt ranking

## Do not use when

- sort only by scanner severity
- hide low-confidence critical candidates

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Load normalized findings, business criticality, ownership, and acceptance criteria.
2. Construct causal and dependency relationships using evidence.
3. Identify minimum root-cause sets that explain material symptoms.
4. Score remediation options across risk, value, cost, machine wall-clock, and reversibility.
5. Test ranking sensitivity to uncertain assumptions.
6. Publish a prioritized risk-reduction backlog with rationale.

## Required outputs

- root-cause graph
- prioritized remediation backlog
- ranking sensitivity
- quick-win set
- strategic workstreams

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

- `architecture-maintainability-audit`
- `correctness-concurrency-consistency-audit`
- `security-privacy-supply-chain-audit`
- `data-database-migration-audit`
- `performance-reliability-observability-audit`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
