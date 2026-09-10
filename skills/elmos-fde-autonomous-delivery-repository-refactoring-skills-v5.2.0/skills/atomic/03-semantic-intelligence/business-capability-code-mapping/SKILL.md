---
name: business-capability-code-mapping
description: Map business capabilities, workflows, rules, decisions, and critical user journeys to code, data, APIs, events, tests, and owners.
---

# Mission

Map business capabilities, workflows, rules, decisions, and critical user journeys to code, data, APIs, events, tests, and owners.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- business capability map
- code ownership
- critical journey
- business rule recovery

## Do not use when

- infer business truth from names alone
- replace domain expert approval

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Load approved workflow and stakeholder evidence.
2. Query the semantic system graph for candidate implementations.
3. Recover rules and state transitions from code, schema, tests, traces, and docs.
4. Validate material mappings with domain owners or authoritative examples.
5. Record confidence, conflicts, and unknowns.
6. Publish capability-to-system and journey-to-test matrices.

## Required outputs

- business capability map
- rule catalog
- critical journey map
- ownership matrix
- traceability matrix

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
- `polyglot-semantic-system-graph`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
