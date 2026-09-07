---
name: numeric-datetime-collation-gate
description: "Run the exact ELMOS Batch 81-95 slightly-strict Numeric, Date-Time and Collation Gate tests with fail-closed native evidence. Use when validating the assigned Language Pack scope."
metadata:
  source_package: "elmos-batch81-95-slightly-strict-test-skills"
  source_id: "T098"
  source_name: "numeric-datetime-collation-gate"
  source_sha256: "sha256:093a1c6b33b154e8a5f4f7805b7ea9cd8b060adea7cbc765240c120b592d18fc"
  source_kind: "cross-gate"
  source_batch: "cross"
  source_version: "1.0.0"
  source_status: "test-ready-not-run"
---


# T098 — Numeric, Date-Time and Collation Gate

## 1. Objective

Detect precision, rounding, overflow, missing/null, timezone, locale, encoding and collation drift.

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
- `PG235`
- `PG236`
- `PG237`
- `PG238`
- `PG239`
- `PG240`
- `PG241`
- `PG242`
- `PG243`
- `PG244`
- `PG245`
- `PG246`
- `PG247`
- `PG248`
- `PG249`
- `PG250`
- `PG251`
- `PG252`
- … plus 150 additional Skills listed in `manifest.json`.

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

- `CASE-0411` [HIGH] Numeric, Date-Time and Collation Gate: Representative path
- `CASE-0412` [HIGH] Numeric, Date-Time and Collation Gate: Boundary path
- `CASE-0413` [HIGH] Numeric, Date-Time and Collation Gate: Invalid or hostile input
- `CASE-0414` [HIGH] Numeric, Date-Time and Collation Gate: Injected dependency failure
- `CASE-0415` [CRITICAL] Numeric, Date-Time and Collation Gate: Security or safety violation
- `CASE-0416` [HIGH] Numeric, Date-Time and Collation Gate: Replay and idempotency
- `CASE-0417` [HIGH] Numeric, Date-Time and Collation Gate: Version or environment drift
- `CASE-0418` [MEDIUM] Numeric, Date-Time and Collation Gate: Moderate scale
- `CASE-0419` [CRITICAL] Numeric, Date-Time and Collation Gate: Evidence tamper
- `CASE-0420` [HIGH] Numeric, Date-Time and Collation Gate: Recovery and final evidence

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
