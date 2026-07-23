---
name: elmos-product-closure-maturity-orchestrator
description: Orchestrate the conversion of Batch 1–55 from a broad capability map
  into a coherent, executable and commercially deliverable product.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A001
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:7fb6be4355cd9a2086c585426633f293d0a2d61f3c3281f9eddcd49bdfcffd5d
  normalized_namespace: product-closure
---

# ELMOS Product Closure & Maturity Orchestrator

## Objective

Orchestrate the conversion of Batch 1–55 from a broad capability map into a coherent, executable and commercially deliverable product.

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

1. Inventory every installed Skill and classify provenance and maturity.
2. Group capabilities into Kernel, Platform, Engine, Domain Pack and Certification Pack.
3. Create the eight closure programs and their dependency DAG.
4. Select three bounded Golden Journeys.
5. Assign owner, budget, environment, tests and evidence.
6. Publish only evidence-backed maturity transitions.

## Required Tests

- `closureGraphRejectsUnknownDependency`
- `programCannotCompleteWithoutRequiredEvidence`
- `planningSkillCannotBeMarkedProductionCertified`
- `criticalRiskBlocksClosure`

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
skill_id: CLO56A001
skill_name: elmos-product-closure-maturity-orchestrator
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
