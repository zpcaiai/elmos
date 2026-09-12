---
name: stakeholder-workflow-discovery
description: Discover stakeholders, current workflows, decisions, pain points, constraints, and measurable outcomes before proposing implementation.
---

# Mission

Discover stakeholders, current workflows, decisions, pain points, constraints, and measurable outcomes before proposing implementation.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- customer discovery
- workflow interview
- stakeholder map
- problem framing

## Do not use when

- implement a known code change
- summarize an already approved specification

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Collect available interviews, notes, tickets, process documents, and system traces.
2. Build a stakeholder and decision-rights map.
3. Reconstruct current-state workflows including exceptions and shadow processes.
4. Quantify pains, delays, errors, cost, risk, and adoption friction where evidence exists.
5. Register contradictions and unknowns instead of resolving them by assumption.
6. Produce a discovery brief and candidate opportunity map for approval.

## Required outputs

- stakeholder map
- current-state workflow
- discovery brief
- opportunity map
- unknown register updates

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

- No local dependency; use the canonical foundation contracts.

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
