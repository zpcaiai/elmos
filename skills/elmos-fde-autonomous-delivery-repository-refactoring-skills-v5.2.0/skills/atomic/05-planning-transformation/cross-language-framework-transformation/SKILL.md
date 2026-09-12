---
name: cross-language-framework-transformation
description: Transform complete repositories across languages or frameworks through Semantic IR, explicit semantic gaps, native runtimes, and differential verification.
---

# Mission

Transform complete repositories across languages or frameworks through Semantic IR, explicit semantic gaps, native runtimes, and differential verification.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- convert repository language
- framework migration
- Java to C#
- Vue to React
- cross-language conversion

## Do not use when

- line-by-line translation
- claim equivalence without native runtime
- erase unsupported semantics

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Validate source and target support profiles and route contract.
2. Extract repository, language, framework, API, data, and build semantics.
3. Plan semantic mappings, shims, manual decisions, and target architecture.
4. Generate in atomic dependency order and compile continuously.
5. Run source-target differential, property, performance, and security verification.
6. Publish gaps, residual risk, generated artifacts, and cutover preparation.

## Required outputs

- target repository
- semantic mapping report
- gap register
- native verification evidence
- migration plan

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
