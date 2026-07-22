---
id: T095
name: batch-95-lua-openresty-slightly-strict-certification
version: 1.0.0
suite: elmos-batch81-95-slightly-strict-tests
kind: batch
batch: 95
severity_policy: non-compensating
target_skill_count: 12
case_count: 26
---

# T095 — Lua OpenResty Embedded Runtime Certification

## 1. Objective

Slightly strict certification for Batch 95 Lua OpenResty Embedded Runtime Certification.

## 2. Scope

This test Skill evaluates the target ELMOS Skills through their public orchestration, artifact, evidence and approval contracts. It does not certify by inspecting file presence alone.

## 3. Target Skills

- `PG391`
- `PG392`
- `PG393`
- `PG394`
- `PG395`
- `PG396`
- `PG397`
- `PG398`
- `PG399`
- `PG400`
- `PG401`
- `PG402`

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

- `CASE-0365` [CRITICAL] Direct verification: PG391 lua project discovery and inventory
- `CASE-0366` [HIGH] Direct verification: PG392 lua parser and semantic model
- `CASE-0367` [HIGH] Direct verification: PG393 openresty nginx application profile
- `CASE-0368` [MEDIUM] Direct verification: PG394 lua embedded host interop generator
- `CASE-0369` [CRITICAL] Direct verification: PG395 lua plugin sandbox capability enforcer
- `CASE-0370` [HIGH] Direct verification: PG396 lua coroutine concurrency modeler
- `CASE-0371` [HIGH] Direct verification: PG397 lua resty http cache gateway generator
- `CASE-0372` [MEDIUM] Direct verification: PG398 lua game embedded scripting profile
- `CASE-0373` [CRITICAL] Direct verification: PG399 lua package build config generator
- `CASE-0374` [HIGH] Direct verification: PG400 lua test fuzz generator
- `CASE-0375` [HIGH] Direct verification: PG401 lua runtime version compatibility checker
- `CASE-0376` [MEDIUM] Direct verification: PG402 lua openresty deployment certifier
- `CASE-0377` [CRITICAL] Compare Lua 5
- `CASE-0378` [HIGH] Attempt metatable, debug library, package loader, FFI and resource-exhaustion sandbox escapes
- `CASE-0379` [HIGH] Exercise yields across C boundaries, cancellation, finalizers and host callback reentrancy
- `CASE-0380` [CRITICAL] Validate Nginx phase restrictions, cosocket use, subrequests and per-worker global state
- `CASE-0381` [HIGH] Inject cache stampede, stale data and cross-tenant key collisions in gateway behavior
- `CASE-0382` [CRITICAL] Validate package provenance, module path isolation, worker reload and zero-downtime deployment
- `CASE-0383` [HIGH] Representative certified success path
- `CASE-0384` [HIGH] Boundary and moderate scale
- `CASE-0385` [HIGH] Invalid and conflicting input
- `CASE-0386` [HIGH] Dependency failure and recovery
- `CASE-0387` [CRITICAL] Security and isolation
- `CASE-0388` [HIGH] Replay and idempotency
- `CASE-0389` [HIGH] Toolchain and version drift
- `CASE-0390` [CRITICAL] Evidence tamper and anti-fraud

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
