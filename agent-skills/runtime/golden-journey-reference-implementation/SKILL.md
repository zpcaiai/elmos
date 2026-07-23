---
name: golden-journey-reference-implementation
description: Implement production-shaped reference journeys that prove cross-Batch
  behavior through real services, failures, recovery and evidence.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A004
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:9347914e711cf5ad821862bc5764228725c3d7bb790e7217ac3279570dd94753
  normalized_namespace: product-closure
---

# Golden Journey Reference Implementation

## Objective

Implement production-shaped reference journeys that prove cross-Batch behavior through real services, failures, recovery and evidence.

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

1. Select representative code-modernization, composite-modernization and safe-agent journeys.
2. Pin exact repositories, databases, providers and environments.
3. Create reproducible fixtures.
4. Execute through control, execution, provider and evidence planes.
5. Inject negative, timeout, cancellation and rollback scenarios.
6. Publish independently accepted evidence packs.

## Required Tests

- `journeyReplaysFromPinnedInputs`
- `failedStepProducesRecoverableState`
- `evidenceCoversEveryCriticalStep`
- `providerOutageDoesNotCorruptJourney`

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
skill_id: CLO56A004
skill_name: golden-journey-reference-implementation
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
