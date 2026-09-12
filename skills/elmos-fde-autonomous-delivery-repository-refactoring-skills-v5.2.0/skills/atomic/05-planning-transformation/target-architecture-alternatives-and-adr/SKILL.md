---
name: target-architecture-alternatives-and-adr
description: Design conservative, balanced, and strategic target architectures with tradeoffs, migration boundaries, ADRs, and exit conditions.
---

# Mission

Design conservative, balanced, and strategic target architectures with tradeoffs, migration boundaries, ADRs, and exit conditions.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- target architecture
- ADR
- refactoring options
- modernization design

## Do not use when

- single unqualified rewrite recommendation
- technology choice without constraints

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Load root causes, invariants, support profile, constraints, and business priorities.
2. Generate feasible architecture alternatives without changing canonical Elmos owners.
3. Evaluate each alternative against functional, security, data, reliability, cost, and adoption criteria.
4. Design transition states, compatibility layers, and rollback boundaries.
5. Write ADRs for material decisions and unresolved tradeoffs.
6. Submit the selected target state for approval.

## Required outputs

- architecture alternatives
- selected target architecture
- ADR set
- transition architecture
- decision approval packet

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

- `root-cause-risk-prioritization`
- `business-invariant-recovery`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
