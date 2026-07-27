---
name: b56-product-experience-role-workspaces-and-onboarding
description: Create role-based workspaces, product navigation, onboarding, demo data,
  explainability, evidence rooms and decision-focused user experience.
metadata:
  source_package: elmos-codex-skills-batch56-product-closure
  source_id: C56-11
  source_name: product-experience-role-workspaces-and-onboarding
  source_batch: '56'
  source_maturity: reviewed-implementation-guidance
  source_sha256: sha256:0143002046980259fefe3cbbf68f488f78845481fc74ae87f6b93f73d336f731
  normalized_namespace: product-batch56-reviewed-guidance
  activation_default: inactive
  readiness_authority: product-batch56a
---

# Product Experience Role Workspaces And Onboarding


## Objective
Create role-based workspaces, product navigation, onboarding, demo data, explainability, evidence rooms and decision-focused user experience.

## Scope
This Skill operates across the Batch 1–55 capability estate and the executable ELMOS product repository. It must preserve source provenance, tenant isolation, auditability and evidence semantics.

## Preconditions
- Batch 1–55 manifest is available.
- Current product repository and runtime architecture are inventoried.
- Existing Skills are classified by provenance and maturity.
- No production write is executed without policy and approval.

## Workflow
1. Discover the current implementation and authoritative manifests.
2. Map relevant Skills, services, contracts, schemas, workflows and providers.
3. Detect duplicate concepts, conflicting definitions and missing runtime paths.
4. Produce a versioned implementation plan with dependencies and rollback.
5. Implement the smallest complete production-shaped vertical slice.
6. Add tests, negative controls, runtime telemetry and immutable evidence.
7. Run integration, holdout, failure and recovery verification.
8. Record remaining gaps and leave the capability at the strongest evidence-backed maturity state.

## Required Outputs
- versioned design or registry artifact;
- implementation changes;
- migration or compatibility plan;
- automated tests;
- runtime evidence references;
- risk and exception findings;
- completion report.

## Required Tests
- positive path;
- negative authorization path;
- duplicate/idempotency path;
- timeout and unknown-result path where applicable;
- rollback or compensation path;
- cross-tenant isolation;
- schema/version compatibility;
- evidence tamper detection;
- representative workload;
- holdout or independent verification.

## Verification
Do not claim completion from static files alone. Verify real builds, runtime behavior, provider contracts and state transitions where the target environment supports them. Mark unavailable checks as NOT_RUN rather than PASS.

## Stop and Escalate
Stop when:
- an authoritative object or system of record is undefined;
- two active Skills claim incompatible ownership;
- a required provider or runtime is unavailable;
- rollback cannot be demonstrated;
- a P0 invariant fails;
- production data or secrets could be exposed;
- evidence is missing or stale.

## Definition of Done
- ownership and boundaries are explicit;
- implementation is integrated into the actual repository;
- critical paths are tested;
- runtime evidence is immutable and traceable;
- rollback/recovery is demonstrated;
- maturity status is evidence-backed;
- unresolved risks are visible and assigned.

## Completion Report
Report implemented scope, tests executed, evidence IDs, maturity state, blocked items, residual risks and the next smallest closure step.

## Repository Integration Boundary

- This installed Skill is reviewed implementation guidance, not evidence that the capability exists.
- Its activation default is `inactive` because Product 56A already owns the overlapping closure capability.
- Source identity remains `C56-11` / `product-experience-role-workspaces-and-onboarding`; the installed alias only resolves naming constraints.
- Product readiness authority remains `scripts/product-closure-batch56a/run_product_closure_gate.py`.
- `NOT_RUN`, unknown, partial, synthetic or self-verified evidence is non-success.
- This Skill cannot approve GA, production certification, deployment or customer acceptance.
