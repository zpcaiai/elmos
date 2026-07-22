---
id: T081
name: batch-81-cobol-mainframe-slightly-strict-certification
version: 1.0.0
suite: elmos-batch81-95-slightly-strict-tests
kind: batch
batch: 81
severity_policy: non-compensating
target_skill_count: 12
case_count: 26
---

# T081 — COBOL Mainframe Modernization Certification

## 1. Objective

Slightly strict certification for Batch 81 COBOL Mainframe Modernization Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG223`
- `PG224`
- `PG225`
- `PG226`
- `PG227`
- `PG228`
- `PG229`
- `PG230`
- `PG231`
- `PG232`
- `PG233`
- `PG234`

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

- `CASE-0001` [CRITICAL] Direct verification: PG223 mainframe estate discovery and inventory
- `CASE-0002` [HIGH] Direct verification: PG224 cobol parser and semantic model
- `CASE-0003` [HIGH] Direct verification: PG225 copybook canonical schema compiler
- `CASE-0004` [MEDIUM] Direct verification: PG226 jcl batch workflow modeler
- `CASE-0005` [CRITICAL] Direct verification: PG227 cics transaction modernizer
- `CASE-0006` [HIGH] Direct verification: PG228 ims vsam db2 data adapter
- `CASE-0007` [HIGH] Direct verification: PG229 cobol business rule recovery
- `CASE-0008` [MEDIUM] Direct verification: PG230 mainframe api event extractor
- `CASE-0009` [CRITICAL] Direct verification: PG231 cobol to java dotnet generator
- `CASE-0010` [HIGH] Direct verification: PG232 mainframe parallel run verifier
- `CASE-0011` [HIGH] Direct verification: PG233 mainframe security operations mapper
- `CASE-0012` [MEDIUM] Direct verification: PG234 mainframe cutover decommission planner
- `CASE-0013` [CRITICAL] Validate nested COPYBOOK REDEFINES, OCCURS DEPENDING ON, packed decimal and EBCDIC conversion without layout loss
- `CASE-0014` [HIGH] Execute JCL with condition codes, restart points, GDG generations and partial rerun without duplicate side effects
- `CASE-0015` [HIGH] Compare pseudo-conversational CICS COMMAREA transaction behavior, syncpoints and error paths against the modernized API
- `CASE-0016` [CRITICAL] Verify packed/zoned decimal rounding, sign handling, date windows and collating sequence on golden financial records
- `CASE-0017` [HIGH] Run source and target in parallel, reconcile records and prove all unexplained differences are below approved thresholds
- `CASE-0018` [CRITICAL] Validate RACF/ACF2 role mapping, least privilege, reversible cutover and protected decommission evidence
- `CASE-0019` [HIGH] Representative certified success path
- `CASE-0020` [HIGH] Boundary and moderate scale
- `CASE-0021` [HIGH] Invalid and conflicting input
- `CASE-0022` [HIGH] Dependency failure and recovery
- `CASE-0023` [CRITICAL] Security and isolation
- `CASE-0024` [HIGH] Replay and idempotency
- `CASE-0025` [HIGH] Toolchain and version drift
- `CASE-0026` [CRITICAL] Evidence tamper and anti-fraud

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
