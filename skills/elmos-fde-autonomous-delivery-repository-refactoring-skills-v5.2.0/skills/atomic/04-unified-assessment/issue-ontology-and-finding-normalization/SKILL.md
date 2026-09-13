---
name: issue-ontology-and-finding-normalization
description: Normalize deterministic and model-generated observations into evidence-backed findings, root causes, relationships, and explicit false-positive risk.
---

# Mission

Normalize deterministic and model-generated observations into evidence-backed findings, root causes, relationships, and explicit false-positive risk.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- normalize findings
- issue ontology
- repository assessment
- problem register

## Do not use when

- paste scanner output
- create unsupported finding
- assign severity without impact context

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Import observations from analyzers, tests, traces, humans, and documents.
2. Validate evidence identity, freshness, location, and reproducibility.
3. Map each observation to the canonical issue taxonomy.
4. Deduplicate and build symptom, cause, dependency, and amplification relationships.
5. Score severity, likelihood, blast radius, business impact, confidence, and false-positive risk.
6. Publish findings and unresolved review queues.

## Required outputs

- normalized finding register
- root-cause graph
- deduplication map
- review queue
- coverage by issue domain

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

- `static-dynamic-evidence-fusion`
- `support-profile-and-unknown-register`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
