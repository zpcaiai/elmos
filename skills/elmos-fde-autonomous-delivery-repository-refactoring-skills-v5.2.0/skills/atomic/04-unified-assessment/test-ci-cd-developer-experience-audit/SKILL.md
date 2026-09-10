---
name: test-ci-cd-developer-experience-audit
description: Audit test strategy, oracle quality, flakiness, fixtures, coverage, mutation resistance, build pipelines, release controls, and developer feedback loops.
---

# Mission

Audit test strategy, oracle quality, flakiness, fixtures, coverage, mutation resistance, build pipelines, release controls, and developer feedback loops.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- test audit
- CI audit
- flaky tests
- coverage gap
- developer experience

## Do not use when

- equate line coverage with correctness
- disable failing tests to pass

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Inventory suites, commands, environments, test data, and pipeline stages.
2. Build requirement-to-test and change-to-test traceability.
3. Run tests repeatedly and under controlled perturbations to identify flakiness.
4. Measure assertion, mutation, fixture, and critical-journey coverage.
5. Analyze pipeline failures, duration, cache, approvals, and artifact provenance.
6. Publish findings and a prioritized quality-engineering plan.

## Required outputs

- test quality assessment
- coverage matrix
- flakiness report
- pipeline assessment
- quality backlog

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
- `reproducible-build-environment`
- `business-capability-code-mapping`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
