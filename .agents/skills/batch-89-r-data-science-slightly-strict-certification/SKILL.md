---
name: batch-89-r-data-science-slightly-strict-certification
description: "Run the exact ELMOS Batch 81-95 slightly-strict R Statistical Reproducibility Certification tests with fail-closed native evidence. Use when validating the assigned Language Pack scope."
metadata:
  source_package: "elmos-batch81-95-slightly-strict-test-skills"
  source_id: "T089"
  source_name: "batch-89-r-data-science-slightly-strict-certification"
  source_sha256: "sha256:4b32f1ff3204ceff597cf27fc61d6c246ffcff06278b88f241ab461c7c8c00e2"
  source_kind: "batch"
  source_batch: "89"
  source_version: "1.0.0"
  source_status: "test-ready-not-run"
---


# T089 — R Statistical Reproducibility Certification

## 1. Objective

Slightly strict certification for Batch 89 R Statistical Reproducibility Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG319`
- `PG320`
- `PG321`
- `PG322`
- `PG323`
- `PG324`
- `PG325`
- `PG326`
- `PG327`
- `PG328`
- `PG329`
- `PG330`

## 4. Inputs

- Target package manifest and exact source fingerprints.
- Isolated tenant, workspace, repository/model estate and platform fixture.
- Pinned compiler, runtime, vendor tooling, dependencies and environment images.
- Test case catalog entries assigned to this Skill.
- Applicable safety, security, compatibility and evidence policies.

## 5. Outputs

- Machine-readable case results and severity classification.
- Source-versus-target semantic and artifact diffs.
- Runtime, simulation, migration, build or platform evidence as applicable.
- Security and safety findings.
- Coverage and release-gate contribution.

## 6. Preconditions

- The source package hash is verified.
- Required vendor tools or simulators are licensed and isolated.
- Fixtures contain no production credentials or real regulated data.
- Audit, trace and evidence capture are enabled.
- The evaluator is independent from the generator for critical assertions.

## 7. Test Portfolio

- `CASE-0209` [CRITICAL] Direct verification: PG319 r project package discovery
- `CASE-0210` [HIGH] Direct verification: PG320 r parser and semantic model
- `CASE-0211` [HIGH] Direct verification: PG321 renv reproducibility planner
- `CASE-0212` [MEDIUM] Direct verification: PG322 tidyverse datatable pipeline modeler
- `CASE-0213` [CRITICAL] Direct verification: PG323 r package project generator
- `CASE-0214` [HIGH] Direct verification: PG324 quarto rmarkdown report generator
- `CASE-0215` [HIGH] Direct verification: PG325 shiny application generator
- `CASE-0216` [MEDIUM] Direct verification: PG326 plumber api generator
- `CASE-0217` [CRITICAL] Direct verification: PG327 targets workflow generator
- `CASE-0218` [HIGH] Direct verification: PG328 testthat statistical test generator
- `CASE-0219` [HIGH] Direct verification: PG329 r python julia interop bridge
- `CASE-0220` [MEDIUM] Direct verification: PG330 statistical reproducibility certifier
- `CASE-0221` [CRITICAL] Restore from renv lock in a clean environment with unavailable cache and detect unpinned system dependencies
- `CASE-0222` [HIGH] Verify NA/NaN/Inf, factors, ordered factors, locale and timezone behavior
- `CASE-0223` [HIGH] Compare tidyverse/data
- `CASE-0224` [CRITICAL] Repeat sequential and parallel RNG workflows with pinned RNGkind and seeds
- `CASE-0225` [HIGH] Detect reactive loops, session data leakage, unsafe HTML and unauthorized download endpoints
- `CASE-0226` [CRITICAL] Compare estimates, confidence intervals, p-values and model predictions within justified tolerances
- `CASE-0227` [HIGH] Representative certified success path
- `CASE-0228` [HIGH] Boundary and moderate scale
- `CASE-0229` [HIGH] Invalid and conflicting input
- `CASE-0230` [HIGH] Dependency failure and recovery
- `CASE-0231` [CRITICAL] Security and isolation
- `CASE-0232` [HIGH] Replay and idempotency
- `CASE-0233` [HIGH] Toolchain and version drift
- `CASE-0234` [CRITICAL] Evidence tamper and anti-fraud

## 8. Environment Matrix

- Clean Linux and/or Windows/macOS environment where the platform requires it.
- Pinned primary supported runtime and one drifted supported/unsupported version.
- Empty, representative and boundary-size project or estate.
- Real compatible database, broker, simulator, VM, ERP/CRM sandbox or vendor runtime where certification requires it.
- Network failure, storage failure and process interruption profiles.

## 9. Fixtures and Data

- Golden source projects and models with known semantic outcomes.
- Adversarial syntax, malformed metadata and version-drift fixtures.
- Boundary numeric, text encoding, date/time, concurrency and state fixtures.
- Security identities with positive and negative privileges.
- Deterministic synthetic data with documented generation seeds.

## 10. Execution Procedure

1. Verify source, toolchain, policy and fixture fingerprints.
2. Start from a clean isolated environment.
3. Execute each assigned case through the supported ELMOS contract.
4. Capture intermediate state, diagnostics, outputs, approvals and evidence.
5. Run real target compilation, simulation or platform validation when required.
6. Compare semantics, state and externally observable behavior.
7. Repeat deterministic successes and replay failure recovery.
8. Publish signed results and coverage updates.

## 11. Assertions

- No silent source construct, business rule, state transition or external side effect is lost.
- No unsupported behavior is represented as certified.
- Security and safety boundaries fail closed.
- Numeric, timing, concurrency and transaction tolerances are justified and versioned.
- Evidence supports every pass, fail, exception and skipped condition.

## 12. Evidence Contract

Evidence includes input and environment hashes, exact tool versions, executed commands or platform operations, logs/traces, semantic diffs, output fingerprints, test assertions, approvals, exceptions and final disposition. A pass without evidence is invalid.

## 13. Failure Classification

- `CRITICAL`: data leakage, unsafe control, secret exposure, evidence fraud, user-owned overwrite, irreversible unapproved change or false certification.
- `HIGH`: semantic drift, incompatible contract, incorrect transaction/state, unrecoverable execution or missing required integration evidence.
- `MEDIUM`: diagnosability, performance or maintainability gap that does not corrupt approved behavior.
- `LOW`: nonblocking presentation or documentation issue.

## 14. Retry, Flakiness and Quarantine

- Retry only documented transient infrastructure failures.
- Deterministic failure cannot be retried into a pass.
- Flaky classification requires repeated evidence and an owner.
- Quarantine never removes a Critical or High case from release criteria.
- Retry history remains visible in the final result.

## 15. Security and Safety Tests

- Least privilege and negative authorization.
- Malicious source, macro, dynamic code, package and metadata inputs.
- Sandbox, FFI, native API and vendor-runtime boundaries.
- Secrets and regulated data redaction.
- Safety-critical or regulated actions require independent approval.

## 16. Anti-Fraud Controls

The suite rejects deleted or disabled failing tests, weakened assertions, enlarged tolerances without approval, mocked mandatory integrations, hidden skips, selective evidence, altered requirements, elevated test-only permissions and self-certification by the generating Agent.

## 17. Acceptance Criteria

- All assigned Critical cases pass.
- High pass rate meets the suite threshold.
- Every target Skill has direct executed coverage.
- Evidence completeness meets the suite threshold.
- No unresolved evidence-integrity, safety or security finding exists.
- Results are reproducible under the pinned environment.

## 18. Definition of Done

This test Skill is complete only when all assigned cases have a final disposition, required evidence is signed and retrievable, coverage is updated, exceptions have owners and expiry, and the aggregate release evaluator has consumed the result.
