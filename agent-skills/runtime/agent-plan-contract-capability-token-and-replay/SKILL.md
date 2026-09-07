---
name: agent-plan-contract-capability-token-and-replay
description: Make agent execution bounded, explainable and replayable using plans,
  task-scoped permissions, governed context and evidence.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A008
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:63b5847c4d343a8baca76baadf210dae5f035990189e827dccd375793839ada3
  normalized_namespace: product-closure
---

# Agent Plan Contract, Capability Token & Replay

## Objective

Make agent execution bounded, explainable and replayable using plans, task-scoped permissions, governed context and evidence.

## Scope

- Implement the capability as a reusable ELMOS platform service.
- Reuse the canonical Kernel, Policy, Evidence, Audit and Runner boundaries.
- Preserve source facts and prior evidence.
- Publish only evidence-backed maturity states.

## Preconditions

- Load the authoritative Batch 1–55 manifest and installed Skill Registry.
- Verify Tenant, Identity, Policy, Audit, Evidence and Runner foundations.
- Treat the current repository and runtime evidence as authority.
- Do not treat static package validation as product certification.

## Domain Model

Implement versioned records for the capability, including owner, status, effective period, source reference, correlation, causation and evidence references.

All tenant-scoped records must enforce RLS and tenant-aware foreign keys. Published history is append-only; corrections create new versions.

## Invariants

- `not_run` is never equivalent to pass.
- Planning-edition Skills cannot claim production certification.
- Provider observations do not overwrite canonical historical facts.
- Critical unknowns block promotion.
- Human approvals are bound to exact input versions.
- P0 failures are non-waivable.

## Workflow

1. Require a plan before nontrivial side effects.
2. Resolve capabilities and approvals.
3. Issue short-lived resource-scoped capability tokens.
4. Build a classified context manifest.
5. Execute typed tools within budget and sandbox.
6. Persist decisions, calls, results and artifacts for replay.

## Required Tests

- `agentWithoutPlanCannotMutate`
- `capabilityTokenCannotEscapeResourceScope`
- `expiredTokenFailsClosed`
- `replayReconstructsExecutionFacts`

Also test tenant isolation, invalid transitions, duplicate delivery, timeout, `UNKNOWN_RESULT`, cancellation, compensation, replay, upgrade and rollback where applicable.

## Verification

Produce a machine-readable result, immutable evidence manifest, trace and artifact references, open findings, exact code/data/environment/tool/policy versions and the strongest evidence-backed maturity decision.

Reject fabricated passes, stale evidence, missing sources, self-approved critical waivers and any P0 waiver.

## Stop and Escalate

- Stop when a canonical invariant, tenant boundary, legal/accounting fact, safety control or irreversible customer state is unresolved.
- Stop when runtime evidence cannot be obtained for a claimed maturity state.
- Escalate conflicts to the accountable architecture, security, legal, finance or domain owner.

## Definition of Done

- The capability is implemented through the approved shared boundaries.
- Required tests have executed with no unapproved P0/P1 failure.
- Evidence is immutable, current and independently reviewable.
- Upgrade, rollback and operational ownership are explicit.

## Completion Report

```yaml
skill_id: CLO56A008
skill_name: agent-plan-contract-capability-token-and-replay
status: BLOCKED|CONDITIONAL|COMPLETED
maturity_before: string
maturity_after: string
tests:
  passed: 0
  failed: 0
  not_run: 0
evidence_refs: []
open_findings: []
waivers: []
rollback_verified: false
next_actions: []
```
