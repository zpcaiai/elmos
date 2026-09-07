---
name: batch-92-objective-c-swift-slightly-strict-certification
description: "Run the exact ELMOS Batch 81-95 slightly-strict Objective-C to Swift Migration Certification tests with fail-closed native evidence. Use when validating the assigned Language Pack scope."
metadata:
  source_package: "elmos-batch81-95-slightly-strict-test-skills"
  source_id: "T092"
  source_name: "batch-92-objective-c-swift-slightly-strict-certification"
  source_sha256: "sha256:7283d01cba7875ae4919a845de270af064141dcb374bc5f784f6c0d5e9015f60"
  source_kind: "batch"
  source_batch: "92"
  source_version: "1.0.0"
  source_status: "test-ready-not-run"
---


# T092 — Objective-C to Swift Migration Certification

## 1. Objective

Slightly strict certification for Batch 92 Objective-C to Swift Migration Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG355`
- `PG356`
- `PG357`
- `PG358`
- `PG359`
- `PG360`
- `PG361`
- `PG362`
- `PG363`
- `PG364`
- `PG365`
- `PG366`

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

- `CASE-0287` [CRITICAL] Direct verification: PG355 objectivec project discovery
- `CASE-0288` [HIGH] Direct verification: PG356 objectivec parser runtime model
- `CASE-0289` [HIGH] Direct verification: PG357 cocoa cocoatouch framework mapper
- `CASE-0290` [MEDIUM] Direct verification: PG358 arc memory ownership analyzer
- `CASE-0291` [CRITICAL] Direct verification: PG359 objectivec swift interop header generator
- `CASE-0292` [HIGH] Direct verification: PG360 objectivec to swift migrator
- `CASE-0293` [HIGH] Direct verification: PG361 storyboard xib to swiftui modernizer
- `CASE-0294` [MEDIUM] Direct verification: PG362 coredata networking migration generator
- `CASE-0295` [CRITICAL] Direct verification: PG363 gcd operationqueue to swift concurrency migrator
- `CASE-0296` [HIGH] Direct verification: PG364 objectivec regression test generator
- `CASE-0297` [HIGH] Direct verification: PG365 apple binary api compatibility checker
- `CASE-0298` [MEDIUM] Direct verification: PG366 objectivec swift cutover certifier
- `CASE-0299` [CRITICAL] Exercise ARC/MRC boundaries, CF bridging, weak/unowned references and autorelease pools
- `CASE-0300` [HIGH] Verify dynamic selectors, categories, swizzling, KVC/KVO and Objective-C runtime metadata
- `CASE-0301` [HIGH] Validate nullability, lightweight generics and generated Swift bridging headers
- `CASE-0302` [CRITICAL] Detect data races, actor-isolation violations, cancellation loss and deadlocks during GCD migration
- `CASE-0303` [HIGH] Round-trip storyboards/XIBs, outlets, actions, constraints and restoration identifiers
- `CASE-0304` [CRITICAL] Validate public ABI/API and staged Core Data model migration across app versions
- `CASE-0305` [HIGH] Representative certified success path
- `CASE-0306` [HIGH] Boundary and moderate scale
- `CASE-0307` [HIGH] Invalid and conflicting input
- `CASE-0308` [HIGH] Dependency failure and recovery
- `CASE-0309` [CRITICAL] Security and isolation
- `CASE-0310` [HIGH] Replay and idempotency
- `CASE-0311` [HIGH] Toolchain and version drift
- `CASE-0312` [CRITICAL] Evidence tamper and anti-fraud

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
