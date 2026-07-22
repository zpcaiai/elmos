---
id: T087
name: batch-87-vb-office-slightly-strict-certification
version: 1.0.0
suite: elmos-batch81-95-slightly-strict-tests
kind: batch
batch: 87
severity_policy: non-compensating
target_skill_count: 12
case_count: 26
---

# T087 — VB6 VBA VB.NET Modernization Certification

## 1. Objective

Slightly strict certification for Batch 87 VB6 VBA VB.NET Modernization Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG295`
- `PG296`
- `PG297`
- `PG298`
- `PG299`
- `PG300`
- `PG301`
- `PG302`
- `PG303`
- `PG304`
- `PG305`
- `PG306`

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

- `CASE-0157` [CRITICAL] Direct verification: PG295 vb6 project discovery and inventory
- `CASE-0158` [HIGH] Direct verification: PG296 vb6 parser and semantic model
- `CASE-0159` [HIGH] Direct verification: PG297 com activex dependency analyzer
- `CASE-0160` [MEDIUM] Direct verification: PG298 vb forms ui event modeler
- `CASE-0161` [CRITICAL] Direct verification: PG299 vba office macro discovery
- `CASE-0162` [HIGH] Direct verification: PG300 vba 32 64bit compatibility analyzer
- `CASE-0163` [HIGH] Direct verification: PG301 vbnet modernization profile
- `CASE-0164` [MEDIUM] Direct verification: PG302 vb6 to csharp generator
- `CASE-0165` [CRITICAL] Direct verification: PG303 vba to office scripts python powerautomate generator
- `CASE-0166` [HIGH] Direct verification: PG304 access database application modernizer
- `CASE-0167` [HIGH] Direct verification: PG305 windows interop regression verifier
- `CASE-0168` [MEDIUM] Direct verification: PG306 vb modernization certifier
- `CASE-0169` [CRITICAL] Verify Variant coercion, Empty/Null/Nothing, default properties and late binding are preserved or made explicit
- `CASE-0170` [HIGH] Trace On Error Resume Next and Err state; migration must not hide failures or change control flow
- `CASE-0171` [HIGH] Exercise COM apartment threading, reference counting, callbacks and event sink lifetime
- `CASE-0172` [CRITICAL] Validate PtrSafe, LongPtr, Windows API declarations and pointer truncation on 32/64-bit Office
- `CASE-0173` [HIGH] Verify signed macro, Trust Center, protected view and least-privilege automation behavior
- `CASE-0174` [CRITICAL] Compare Access queries, forms, reports and record-locking behavior with the modernized application
- `CASE-0175` [HIGH] Representative certified success path
- `CASE-0176` [HIGH] Boundary and moderate scale
- `CASE-0177` [HIGH] Invalid and conflicting input
- `CASE-0178` [HIGH] Dependency failure and recovery
- `CASE-0179` [CRITICAL] Security and isolation
- `CASE-0180` [HIGH] Replay and idempotency
- `CASE-0181` [HIGH] Toolchain and version drift
- `CASE-0182` [CRITICAL] Evidence tamper and anti-fraud

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
