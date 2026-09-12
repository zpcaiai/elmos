---
name: final-handoff-training-support
description: Create technical and operational handoff, training, support ownership, runbooks, knowledge transfer, and exit criteria for delivered work.
---

# Mission

Create technical and operational handoff, training, support ownership, runbooks, knowledge transfer, and exit criteria for delivered work.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- handoff
- runbook
- training
- support transition
- knowledge transfer

## Do not use when

- declare handoff complete without owner acceptance
- transfer secrets in documents

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Inventory required operating knowledge, responsibilities, and access.
2. Generate role-specific runbooks, diagrams, training, and checklists.
3. Run knowledge-transfer sessions and operational exercises.
4. Record gaps, questions, and remediation actions.
5. Obtain receiving-owner acceptance against exit criteria.
6. Seal the handoff packet and transition support ownership.

## Required outputs

- handoff packet
- role-specific runbooks
- training assets
- exercise evidence
- ownership acceptance

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

- `adoption-change-management`
- `e0-e3-readiness-and-evidence-bundle`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
