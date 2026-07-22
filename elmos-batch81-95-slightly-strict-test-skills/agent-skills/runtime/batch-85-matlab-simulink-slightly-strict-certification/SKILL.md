---
id: T085
name: batch-85-matlab-simulink-slightly-strict-certification
version: 1.0.0
suite: elmos-batch81-95-slightly-strict-tests
kind: batch
batch: 85
severity_policy: non-compensating
target_skill_count: 12
case_count: 26
---

# T085 — MATLAB Simulink Stateflow Certification

## 1. Objective

Slightly strict certification for Batch 85 MATLAB Simulink Stateflow Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG271`
- `PG272`
- `PG273`
- `PG274`
- `PG275`
- `PG276`
- `PG277`
- `PG278`
- `PG279`
- `PG280`
- `PG281`
- `PG282`

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

- `CASE-0105` [CRITICAL] Direct verification: PG271 matlab project discovery and inventory
- `CASE-0106` [HIGH] Direct verification: PG272 matlab code parser and semantic model
- `CASE-0107` [HIGH] Direct verification: PG273 simulink model graph compiler
- `CASE-0108` [MEDIUM] Direct verification: PG274 stateflow semantics and transition modeler
- `CASE-0109` [CRITICAL] Direct verification: PG275 simscape data dictionary integrator
- `CASE-0110` [HIGH] Direct verification: PG276 algorithm to matlab project generator
- `CASE-0111` [HIGH] Direct verification: PG277 natural language to simulink model generator
- `CASE-0112` [MEDIUM] Direct verification: PG278 matlab python julia interop bridge
- `CASE-0113` [CRITICAL] Direct verification: PG279 matlab coder embedded code generator
- `CASE-0114` [HIGH] Direct verification: PG280 sil pil hil test harness generator
- `CASE-0115` [HIGH] Direct verification: PG281 numerical equivalence verifier
- `CASE-0116` [MEDIUM] Direct verification: PG282 model code traceability certifier
- `CASE-0117` [CRITICAL] Validate inherited, discrete and continuous sample times, rate transitions and multirate scheduling
- `CASE-0118` [HIGH] Exercise transition priority, temporal logic, history junctions, events and parallel states
- `CASE-0119` [HIGH] Compare fixed-point scaling, saturation, wraparound and generated-code overflow behavior
- `CASE-0120` [CRITICAL] Detect algebraic loops, solver differences and hidden initial-condition sensitivity
- `CASE-0121` [HIGH] Compare model, generated code and target execution under SIL/PIL/HIL with approved numeric tolerances
- `CASE-0122` [CRITICAL] Repeat stochastic simulations with pinned random streams, datasets and solver versions
- `CASE-0123` [HIGH] Representative certified success path
- `CASE-0124` [HIGH] Boundary and moderate scale
- `CASE-0125` [HIGH] Invalid and conflicting input
- `CASE-0126` [HIGH] Dependency failure and recovery
- `CASE-0127` [CRITICAL] Security and isolation
- `CASE-0128` [HIGH] Replay and idempotency
- `CASE-0129` [HIGH] Toolchain and version drift
- `CASE-0130` [CRITICAL] Evidence tamper and anti-fraud

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
