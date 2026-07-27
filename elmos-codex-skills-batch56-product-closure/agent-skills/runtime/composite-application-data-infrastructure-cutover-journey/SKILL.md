---
name: composite-application-data-infrastructure-cutover-journey
description: Implement coordinated application, database, messaging, infrastructure and security modernization as one dependency-aware composite change set and cutover journey.
---

# Composite Application Data Infrastructure Cutover Journey


## Objective
Implement coordinated application, database, messaging, infrastructure and security modernization as one dependency-aware composite change set and cutover journey.

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
