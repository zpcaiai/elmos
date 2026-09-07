---
name: batch-91-salesforce-slightly-strict-certification
description: "Run the exact ELMOS Batch 81-95 slightly-strict Salesforce Apex LWC Release Certification tests with fail-closed native evidence. Use when validating the assigned Language Pack scope."
metadata:
  source_package: "elmos-batch81-95-slightly-strict-test-skills"
  source_id: "T091"
  source_name: "batch-91-salesforce-slightly-strict-certification"
  source_sha256: "sha256:893ca368a9efa32ecd125c291e0578acc47953f27a7a9a51f6ddcde88d04b611"
  source_kind: "batch"
  source_batch: "91"
  source_version: "1.0.0"
  source_status: "test-ready-not-run"
---


# T091 — Salesforce Apex LWC Release Certification

## 1. Objective

Slightly strict certification for Batch 91 Salesforce Apex LWC Release Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG343`
- `PG344`
- `PG345`
- `PG346`
- `PG347`
- `PG348`
- `PG349`
- `PG350`
- `PG351`
- `PG352`
- `PG353`
- `PG354`

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

- `CASE-0261` [CRITICAL] Direct verification: PG343 salesforce org metadata discovery
- `CASE-0262` [HIGH] Direct verification: PG344 apex parser and semantic model
- `CASE-0263` [HIGH] Direct verification: PG345 soql sosl query analyzer
- `CASE-0264` [MEDIUM] Direct verification: PG346 trigger bulkification governor limit analyzer
- `CASE-0265` [CRITICAL] Direct verification: PG347 lwc application generator
- `CASE-0266` [HIGH] Direct verification: PG348 visualforce to lwc modernizer
- `CASE-0267` [HIGH] Direct verification: PG349 flow apex orchestration generator
- `CASE-0268` [MEDIUM] Direct verification: PG350 platform event integration generator
- `CASE-0269` [CRITICAL] Direct verification: PG351 salesforce security sharing fsl crud generator
- `CASE-0270` [HIGH] Direct verification: PG352 sfdx package ci generator
- `CASE-0271` [HIGH] Direct verification: PG353 apex test mutation generator
- `CASE-0272` [MEDIUM] Direct verification: PG354 salesforce release certifier
- `CASE-0273` [CRITICAL] Execute 200-record bulk operations and verify SOQL, DML, CPU, heap and callout limits remain safe
- `CASE-0274` [HIGH] Detect trigger recursion, order-of-execution errors and mixed-DML violations
- `CASE-0275` [HIGH] Run with profiles, permission sets, sharing rules and restricted fields; enforce CRUD/FLS and record sharing
- `CASE-0276` [CRITICAL] Inject dynamic SOQL/SOSL inputs and nonselective queries; reject unsafe or governor-risk code
- `CASE-0277` [HIGH] Exercise Queueable, Batch, Future and Platform Event ordering, retries and duplicate delivery
- `CASE-0278` [CRITICAL] Install in a clean scratch org and validate namespace, metadata dependency and destructive-change behavior
- `CASE-0279` [HIGH] Representative certified success path
- `CASE-0280` [HIGH] Boundary and moderate scale
- `CASE-0281` [HIGH] Invalid and conflicting input
- `CASE-0282` [HIGH] Dependency failure and recovery
- `CASE-0283` [CRITICAL] Security and isolation
- `CASE-0284` [HIGH] Replay and idempotency
- `CASE-0285` [HIGH] Toolchain and version drift
- `CASE-0286` [CRITICAL] Evidence tamper and anti-fraud

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
