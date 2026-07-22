---
name: batch-83-database-procedural-slightly-strict-certification
description: "Run the exact ELMOS Batch 81-95 slightly-strict Database Procedural Logic Certification tests with fail-closed native evidence. Use when validating the assigned Language Pack scope."
metadata:
  source_package: "elmos-batch81-95-slightly-strict-test-skills"
  source_id: "T083"
  source_name: "batch-83-database-procedural-slightly-strict-certification"
  source_sha256: "sha256:25a63e39d2dc2081e6ed2052048f533d98301fbf32b1833c0343b74ec4390873"
  source_kind: "batch"
  source_batch: "83"
  source_version: "1.0.0"
  source_status: "test-ready-not-run"
---


# T083 — Database Procedural Logic Certification

## 1. Objective

Slightly strict certification for Batch 83 Database Procedural Logic Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG247`
- `PG248`
- `PG249`
- `PG250`
- `PG251`
- `PG252`
- `PG253`
- `PG254`
- `PG255`
- `PG256`
- `PG257`
- `PG258`

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

- `CASE-0053` [CRITICAL] Direct verification: PG247 database program unit discovery
- `CASE-0054` [HIGH] Direct verification: PG248 plsql parser and semantic model
- `CASE-0055` [HIGH] Direct verification: PG249 tsql parser and semantic model
- `CASE-0056` [MEDIUM] Direct verification: PG250 plpgsql sqlpl parser and semantic model
- `CASE-0057` [CRITICAL] Direct verification: PG251 stored procedure business rule extractor
- `CASE-0058` [HIGH] Direct verification: PG252 trigger job dblink impact analyzer
- `CASE-0059` [HIGH] Direct verification: PG253 dynamic sql injection safety analyzer
- `CASE-0060` [MEDIUM] Direct verification: PG254 database logic retain refactor extract decider
- `CASE-0061` [CRITICAL] Direct verification: PG255 procedure to service generator
- `CASE-0062` [HIGH] Direct verification: PG256 database code test harness generator
- `CASE-0063` [HIGH] Direct verification: PG257 transaction concurrency equivalence verifier
- `CASE-0064` [MEDIUM] Direct verification: PG258 database program modernization certifier
- `CASE-0065` [CRITICAL] Inject hostile identifiers, predicates and search paths into dynamic SQL; generation must parameterize or reject safely
- `CASE-0066` [HIGH] Validate recursive/cascading trigger order, disabled-trigger assumptions and job side effects
- `CASE-0067` [HIGH] Compare commit, rollback, savepoint, isolation, lock and deadlock behavior between source and extracted service
- `CASE-0068` [CRITICAL] Vary NLS, DATEFORMAT, search_path, collation and timezone to detect session-dependent semantics
- `CASE-0069` [HIGH] Verify ref cursors, table-valued results, output parameters, result-set ordering and null semantics
- `CASE-0070` [CRITICAL] Run database procedure and generated service against identical snapshots and reconcile all state changes
- `CASE-0071` [HIGH] Representative certified success path
- `CASE-0072` [HIGH] Boundary and moderate scale
- `CASE-0073` [HIGH] Invalid and conflicting input
- `CASE-0074` [HIGH] Dependency failure and recovery
- `CASE-0075` [CRITICAL] Security and isolation
- `CASE-0076` [HIGH] Replay and idempotency
- `CASE-0077` [HIGH] Toolchain and version drift
- `CASE-0078` [CRITICAL] Evidence tamper and anti-fraud

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
