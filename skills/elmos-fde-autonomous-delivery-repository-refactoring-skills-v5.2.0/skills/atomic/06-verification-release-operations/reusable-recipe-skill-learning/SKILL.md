---
name: reusable-recipe-skill-learning
description: Extract proven project patterns into reusable recipes, skills, fixtures, rules, and adapters without leaking tenant data or duplicating canonical capabilities.
---

# Mission

Extract proven project patterns into reusable recipes, skills, fixtures, rules, and adapters without leaking tenant data or duplicating canonical capabilities.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- learn recipe
- create reusable skill
- postmortem improvement
- pattern extraction

## Do not use when

- train globally without consent
- create duplicate skill
- generalize from one weak example

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Collect material lessons from deliveries, incidents, reviews, and repeated manual corrections.
2. Classify the correct improvement owner: AGENTS, harness, existing Skill, reference, script, test, adapter, policy, new Skill, or no change.
3. Check duplication and canonical ownership across the capability graph.
4. Create sanitized candidate artifacts and eval cases.
5. Run deterministic and rubric-based evaluations with negative controls.
6. Release only after independent acceptance and versioned invalidation rules.

## Required outputs

- reusable recipe
- Skill or adapter update
- eval suite
- non-duplication decision
- learning provenance

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

- `incident-triage-remediation-and-postmortem`
- `e0-e3-readiness-and-evidence-bundle`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
