---
name: execution-reliability-state-protocol-hardening
description: Unify leases, retries, cancellation, pause/resume, unknown results, compensation,
  replay and reconciliation.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A006
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:2d2c316ac7eb85af7307ab012c599cde2de9c26b7d20df91b3616c8d5d53dc15
  normalized_namespace: product-closure
---

# Execution Reliability & State Protocol Hardening

## Objective

Unify leases, retries, cancellation, pause/resume, unknown results, compensation, replay and reconciliation.

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

1. Adopt the canonical execution state protocol.
2. Bind every side effect to operation and idempotency IDs.
3. Persist attempts and observations append-only.
4. Classify failures as retryable, final or reconcile-first.
5. Implement cancellation and compensation boundaries.
6. Run crash, duplicate-delivery and timeout campaigns.

## Required Tests

- `timeoutAfterProviderAcceptanceDoesNotDuplicate`
- `expiredLeaseIsSafelyRecovered`
- `cancellationDoesNotLoseObservedEffects`
- `unknownResultRequiresReconciliation`

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
skill_id: CLO56A006
skill_name: execution-reliability-state-protocol-hardening
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
