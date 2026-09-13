---
name: product-feedback-roadmap-loop
description: Convert delivery evidence, adoption, failures, customer requests, and recurring gaps into evidence-ranked product roadmap inputs.
---

# Mission

Convert delivery evidence, adoption, failures, customer requests, and recurring gaps into evidence-ranked product roadmap inputs.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- product feedback
- roadmap input
- customer request synthesis
- delivery learning

## Do not use when

- promise roadmap date
- rank by loudest customer only
- mix tenant secrets into shared roadmap

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Collect approved feedback, support, usage, incident, sales, and delivery evidence.
2. Deduplicate problem statements while retaining customer-specific constraints.
3. Map each item to existing capabilities, gaps, adapters, or non-product needs.
4. Score value, recurrence, strategic leverage, risk, and evidence confidence.
5. Prepare roadmap decision packets and candidate experiments.
6. Record product decisions and communicate them back to engagement owners.

## Required outputs

- normalized feedback
- capability gap map
- roadmap decision packet
- experiment proposal
- customer response input

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
- `adoption-change-management`
- `reusable-recipe-skill-learning`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
