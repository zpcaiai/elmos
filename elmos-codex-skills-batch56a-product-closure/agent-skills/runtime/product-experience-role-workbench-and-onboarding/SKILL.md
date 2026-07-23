---
name: product-experience-role-workbench-and-onboarding
description: Design role-based workbenches, first-value onboarding, attention queues, evidence navigation and safe typed actions.
id: CLO56A010
batch: 56A
maturity: reviewed-design
---

# Product Experience, Role Workbench & Onboarding

## Objective

Design role-based workbenches, first-value onboarding, attention queues, evidence navigation and safe typed actions.

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

1. Define primary personas and outcomes.
2. Map Golden Journey steps to workbenches.
3. Create attention, blocker and decision queues.
4. Design typed actions with effect and policy previews.
5. Add evidence drill-down and source lineage.
6. Measure time-to-first-value and task completion.

## Required Tests

- `userSeesOnlyAuthorizedAttentionItems`
- `typedActionDisplaysExpectedEffect`
- `onboardingProducesFirstVerifiedArtifact`
- `criticalBlockerCannotBeHidden`

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
skill_id: CLO56A010
skill_name: product-experience-role-workbench-and-onboarding
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
