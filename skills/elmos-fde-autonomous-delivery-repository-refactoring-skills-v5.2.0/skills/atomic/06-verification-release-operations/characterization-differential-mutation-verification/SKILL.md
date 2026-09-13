---
name: characterization-differential-mutation-verification
description: Build characterization, contract, differential, property, metamorphic, fuzz, mutation, and regression evidence for repository transformations.
---

# Mission

Build characterization, contract, differential, property, metamorphic, fuzz, mutation, and regression evidence for repository transformations.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- verify refactor
- behavior equivalence
- characterization tests
- mutation testing
- differential testing

## Do not use when

- declare success from compile only
- let implementation agent approve itself
- ignore approved behavior changes

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Build a requirement, invariant, risk, and ChangeSet coverage matrix.
2. Generate or import characterization and contract oracles.
3. Execute source and target against representative, adversarial, and historical inputs.
4. Normalize and compare outputs, state, side effects, performance, and security behavior.
5. Run mutation, fuzz, property, and regression campaigns according to risk.
6. Publish claims, counterexamples, coverage, residual unknowns, and verifier decision inputs.

## Required outputs

- verification plan
- differential report
- mutation and fuzz report
- counterexample set
- verification claims

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

- `proof-guided-atomic-refactor-execution`
- `business-invariant-recovery`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
