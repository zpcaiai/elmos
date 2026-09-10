---
name: reproducible-build-environment
description: Infer, pin, reproduce, and diagnose native build and test environments in isolated execution sandboxes.
---

# Mission

Infer, pin, reproduce, and diagnose native build and test environments in isolated execution sandboxes.

This is a non-routable Elmos component Skill. It must execute only through an existing canonical K1-K8 or Domain Pack owner selected by `routeOwnerRef` in `manifest.yaml`.

## Use when

- reproduce build
- build failure
- runtime environment
- toolchain pinning
- native lab

## Do not use when

- declare project broken before environment diagnosis
- run untrusted code outside sandbox

## Required inputs

- Approved TaskContract and acceptance scope
- Tenant and repository identity
- Exact RevisionSet and environment fingerprint
- Policy profile and capability lease
- Relevant system graph, findings, invariants, or evidence

## Workflow

1. Derive candidate build roots and commands from manifests, CI, docs, and history.
2. Resolve toolchain and service prerequisites without exposing secrets to model context.
3. Provision an isolated environment with explicit network and filesystem policy.
4. Run staged dependency resolution, compilation, tests, and packaging.
5. Classify failures and iterate only within approved authority.
6. Seal a reproducible environment fingerprint and build evidence.

## Required outputs

- environment fingerprint
- replayable build plan
- build evidence
- failure taxonomy
- artifact manifest

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

- `asset-inventory-and-classification`

## Read next

- `manifest.yaml` for typed ownership, authority, dependencies, telemetry, and compatibility
- `acceptance.yaml` for independent acceptance and blockers
- `implementation.yaml` for ports, persistence, APIs, events, and tests
- `runbook.md` for operational execution and recovery
- `../../../../docs/00_PACKAGE_SCOPE_AND_BOUNDARIES.md` for package limits
- `../../../../docs/17_NON_DUPLICATION_AND_CANONICAL_OWNERSHIP.md` for K1-K8 integration
