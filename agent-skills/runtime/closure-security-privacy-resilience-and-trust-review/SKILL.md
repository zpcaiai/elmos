---
name: closure-security-privacy-resilience-and-trust-review
description: Perform cross-cutting review of tenant isolation, secrets, privacy, agent
  authority, supply chain, resilience and trust.
metadata:
  source_package: elmos-codex-skills-batch56a-product-closure
  source_id: CLO56A015
  source_batch: 56A
  source_maturity: reviewed-design
  source_sha256: sha256:f163d09cdd8b2908dc0ef0f52ec7b9b84096ea093d5bb3a9fed15ae898a82a9a
  normalized_namespace: product-closure
---

# Closure Security, Privacy, Resilience & Trust Review

## Objective

Perform cross-cutting review of tenant isolation, secrets, privacy, agent authority, supply chain, resilience and trust.

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

1. Update the system threat model.
2. Test tenant, privilege and provider boundaries.
3. Review secrets, keys and artifact supply chain.
4. Review context and evidence minimization.
5. Run dependency and disaster scenarios.
6. Track critical findings to verified remediation.

## Required Tests

- `crossTenantKernelAccessIsRejected`
- `agentCannotEscalateToolAuthority`
- `secretNeverEntersEvidence`
- `criticalTrustFindingBlocksGa`

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
skill_id: CLO56A015
skill_name: closure-security-privacy-resilience-and-trust-review
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
