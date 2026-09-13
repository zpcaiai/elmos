---
name: proof-guided-atomic-refactor-execution
description: Execute approved repository refactors using deterministic transformations first, bounded synthesis second, and proof obligations at every step.
---

# Mission

Execute approved repository refactors using deterministic transformations first, bounded synthesis second, and proof obligations at every step.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- execute refactor
- apply transformation plan
- automated refactoring
- repository-wide change

## Do not use when

- free-form rewrite without plan
- skip failing verification
- production write without approval

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Load one approved DAG step, exact RevisionSet, invariants, and expected delta.
2. Select the highest-confidence deterministic transformation mechanism.
3. Execute in an isolated workspace with tool-result interception.
4. Run step-local compile, static, test, contract, and policy checks.
5. Request independent verification and approval according to risk.
6. Commit or roll back, update ledgers, and release the capability lease.

## Required outputs

- verified patch candidate
- ChangeSet evidence
- updated tests
- execution trace
- rollback outcome

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

- `changeset-commit-and-provenance-governance`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
