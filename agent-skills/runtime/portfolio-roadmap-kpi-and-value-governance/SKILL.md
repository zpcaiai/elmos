---
name: portfolio-roadmap-kpi-and-value-governance
description: Replace Batch-count progress with product outcomes, reliability, economics,
  customer acceptance and evidence.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A014
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:e6979081bcd9ce20f2ab1d80eb1241aa0a7892b7ba887931902a9e8f1046d1f7
  normalized_namespace: product-closure
---

# Portfolio Roadmap, KPI & Value Governance

## Objective

Replace Batch-count progress with product outcomes, reliability, economics, customer acceptance and evidence.

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

1. Define the twelve maturity KPIs.
2. Bind KPI calculations to certified evidence.
3. Create 0–60, 60–150, 150–240 and 240–365 day waves.
4. Score work by value, risk, dependency and evidence gap.
5. Stop low-value horizontal expansion.
6. Publish monthly evidence-backed decisions.

## Required Tests

- `batchCountCannotDriveMaturityScore`
- `kpiRequiresCertifiedSource`
- `criticalJourneyFailureBlocksGreenStatus`
- `roadmapDependencyIsRespected`

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
skill_id: CLO56A014
skill_name: portfolio-roadmap-kpi-and-value-governance
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
