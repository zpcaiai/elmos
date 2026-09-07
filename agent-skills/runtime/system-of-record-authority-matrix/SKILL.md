---
name: system-of-record-authority-matrix
description: Define authoritative ownership, write permissions, projections, conflict
  policy and reconciliation for shared enterprise facts.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A007
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:22c2595f8fbdb1b24bfc970f458916f37a5da68b754cad032e38e5a3a1dfaf25
  normalized_namespace: product-closure
---

# System of Record & Authority Matrix

## Objective

Define authoritative ownership, write permissions, projections, conflict policy and reconciliation for shared enterprise facts.

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

1. Inventory Customer, Contract, Employee, Asset, Product, Payment and other shared records.
2. Assign authoritative system and accountable owner.
3. Define allowed writers and read-only projections.
4. Specify correction, merge and conflict behavior.
5. Implement synchronization and drift detection.
6. Publish authority decisions to dependent Skills.

## Required Tests

- `contractAuthorityCannotBeOverwrittenByCrm`
- `paymentSettlementUsesApprovedFactSource`
- `projectionCannotWriteAuthoritativeField`
- `conflictCreatesReviewCase`

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
skill_id: CLO56A007
skill_name: system-of-record-authority-matrix
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
