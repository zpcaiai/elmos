---
name: batch-88-ibmi-rpg-slightly-strict-certification
description: "Run the exact ELMOS Batch 81-95 slightly-strict IBM i RPG CL DDS Modernization Certification tests with fail-closed native evidence. Use when validating the assigned Language Pack scope."
metadata:
  source_package: "elmos-batch81-95-slightly-strict-test-skills"
  source_id: "T088"
  source_name: "batch-88-ibmi-rpg-slightly-strict-certification"
  source_sha256: "sha256:ce7b9825544ccc95164529d6ff5fdcbe8d5627800b9afd1bb7799d0023d036ff"
  source_kind: "batch"
  source_batch: "88"
  source_version: "1.0.0"
  source_status: "test-ready-not-run"
---


# T088 — IBM i RPG CL DDS Modernization Certification

## 1. Objective

Slightly strict certification for Batch 88 IBM i RPG CL DDS Modernization Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG307`
- `PG308`
- `PG309`
- `PG310`
- `PG311`
- `PG312`
- `PG313`
- `PG314`
- `PG315`
- `PG316`
- `PG317`
- `PG318`

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

- `CASE-0183` [CRITICAL] Direct verification: PG307 ibmi landscape discovery and inventory
- `CASE-0184` [HIGH] Direct verification: PG308 rpg parser and semantic model
- `CASE-0185` [HIGH] Direct verification: PG309 cl job workflow modeler
- `CASE-0186` [MEDIUM] Direct verification: PG310 dds display printer file modeler
- `CASE-0187` [CRITICAL] Direct verification: PG311 db2i data access mapper
- `CASE-0188` [HIGH] Direct verification: PG312 ile service program binding analyzer
- `CASE-0189` [HIGH] Direct verification: PG313 5250 ui to web modernizer
- `CASE-0190` [MEDIUM] Direct verification: PG314 rpg to java dotnet generator
- `CASE-0191` [CRITICAL] Direct verification: PG315 cl to workflow batch generator
- `CASE-0192` [HIGH] Direct verification: PG316 ibmi integration adapter
- `CASE-0193` [HIGH] Direct verification: PG317 ibmi parallel run record verifier
- `CASE-0194` [MEDIUM] Direct verification: PG318 ibmi cutover certifier
- `CASE-0195` [CRITICAL] Verify packed/zoned decimal, CCSID conversion, fixed-length fields and record-format overlays
- `CASE-0196` [HIGH] Exercise RPG indicators, calculation cycle, subprocedures and file operation status codes
- `CASE-0197` [HIGH] Validate OVRDBF, library lists, job attributes, commitment control and restart semantics
- `CASE-0198` [CRITICAL] Verify keyed physical/logical files, display subfiles and printer file formatting
- `CASE-0199` [HIGH] Detect service program binding signature and activation-group compatibility breaks
- `CASE-0200` [CRITICAL] Reconcile source/target records, spool outputs, data queues and batch job effects
- `CASE-0201` [HIGH] Representative certified success path
- `CASE-0202` [HIGH] Boundary and moderate scale
- `CASE-0203` [HIGH] Invalid and conflicting input
- `CASE-0204` [HIGH] Dependency failure and recovery
- `CASE-0205` [CRITICAL] Security and isolation
- `CASE-0206` [HIGH] Replay and idempotency
- `CASE-0207` [HIGH] Toolchain and version drift
- `CASE-0208` [CRITICAL] Evidence tamper and anti-fraud

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
