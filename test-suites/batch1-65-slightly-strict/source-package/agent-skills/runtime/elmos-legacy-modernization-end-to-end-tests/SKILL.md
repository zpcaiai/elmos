---
name: elmos-legacy-modernization-end-to-end-tests
description: "Run slightly strict cross-batch tests for Legacy modernization end-to-end certification."
version: 1.0.0
test_skill_id: T066
strictness_profile: elmos-slightly-strict-v1
case_count: 10
target_batches: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45]
source_package: elmos-skills-batch1-65-complete
---

# T066 — Legacy modernization end-to-end certification Slightly Strict Tests

## 1. Objective

Execute a deterministic, evidence-backed and moderately adversarial certification suite for **Legacy modernization end-to-end certification**. This suite is stricter than a smoke test but does not claim exhaustive formal verification.

## 2. Target Scope

- **Target Batch(es):** 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45
- **Target product line(s):** legacy-modernization, project-synthesis
- **Direct target Skill count:** 1074

- All applicable Skills in Batch 1–45, selected through the target manifest and case tags.

## 3. Strictness Profile

Use `references/STRICTNESS_PROFILE.json` without weakening thresholds. Critical cases are zero-tolerance. High-severity cases require at least 98% pass rate. Overall pass rate must be at least 95%, and every source Skill must retain a direct coverage mapping.

## 4. Inputs

- Installed target ELMOS Batch 1–65 Skills and exact source manifest.
- Test environment identity and capability grant.
- Pinned fixtures, tools, runners, model routes and dependencies.
- Previous compatible baseline where version or regeneration behavior is tested.
- Evidence store and append-only audit channel.

## 5. Required Fixtures

- One valid representative fixture for the target theme.
- One boundary/scale fixture.
- One malformed or contradictory fixture.
- One dependency-failure fixture.
- Two-tenant or two-project isolation fixture.
- Replay/idempotency fixture.
- Compatible and incompatible version-drift fixtures.
- Evidence-tamper fixture.

## 6. Preconditions

- Source package validation status is `PASSED`.
- Target Skills and test Skills are installed without name collision.
- Required real integrations are available when mocks are insufficient for certification.
- System clocks, random seeds and environment variables are controlled where determinism matters.
- Test data contains no production secrets or real regulated personal data.

## 7. Test Cases

### TC-T066-001 — Complete representative workflow satisfies the invariant

- **Category:** `golden_path`
- **Severity:** `HIGH`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to golden_path.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The golden_path scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-002 — Declared boundary and moderate-scale operation satisfy the invariant

- **Category:** `boundary`
- **Severity:** `MEDIUM`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to boundary.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The boundary scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-003 — Invalid or contradictory request is blocked without partial success

- **Category:** `negative`
- **Severity:** `HIGH`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to negative.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The negative scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-004 — A material dependency failure is contained, diagnosed and recoverable

- **Category:** `dependency_failure`
- **Severity:** `HIGH`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to dependency_failure.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The dependency_failure scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-005 — An adversarial actor cannot violate the invariant

- **Category:** `security`
- **Severity:** `CRITICAL`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to security.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The security scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-006 — Replay, retry and resume preserve the invariant without duplication

- **Category:** `replay`
- **Severity:** `HIGH`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to replay.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The replay scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-007 — Compatible drift is accepted and incompatible drift is blocked

- **Category:** `version_drift`
- **Severity:** `HIGH`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to version_drift.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The version_drift scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-008 — Tampered evidence, approval or artifact cannot pass

- **Category:** `tamper`
- **Severity:** `CRITICAL`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to tamper.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The tamper scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-009 — The invariant holds within declared scale and cost budgets

- **Category:** `scale_cost`
- **Severity:** `MEDIUM`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to scale_cost.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The scale_cost scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`

### TC-T066-010 — Rollback, compensation or forward recovery preserves the invariant

- **Category:** `rollback_recovery`
- **Severity:** `HIGH`
- **Setup:** Prepare a representative multi-Batch fixture for Legacy modernization end-to-end certification; include valid baselines plus one controlled adversarial or failure condition appropriate to rollback_recovery.
- **Stimulus:** Execute the connected workflows spanning Batch 1–45 and evaluate the invariant across every boundary crossed by the case.
- **Expected result:** A representative legacy repository progresses from intake through modernization, equivalence validation, cutover, audit and operations without losing lineage or safety. The rollback_recovery scenario produces a deterministic pass or an explicit blocking finding; no hidden partial success is permitted.
- **Deterministic oracle:** Use schema/parser validation, stable identifiers, stored baseline comparison, explicit state/permission checks, content hashes and recorded runner/tool exit status. LLM interpretation may explain a finding but cannot determine raw pass/fail facts.
- **Required evidence:**
  - input and fixture fingerprints
  - target Skill and tool versions
  - structured execution events
  - raw validator or runner output
  - Artifact Graph or trace links where applicable
  - output fingerprints
  - policy and approval decisions
  - final deterministic assertion record
- **Disallowed shortcuts:**
  - `delete_or_disable_test`
  - `weaken_assertion`
  - `change_approved_requirement`
  - `hide_warning_or_skip`
  - `fabricate_evidence`
  - `use_mock_in_place_of_required_real_integration`
  - `write_user_owned_code`
  - `grant_extra_permission_to_make_test_pass`


## 8. Deterministic Oracles

- Prefer schemas, parsers, compiler exit codes, database constraints, stable graph queries, cryptographic hashes, permission decisions, state-transition validators and byte/semantic diffs.
- LLM output may classify or explain evidence only after raw facts are preserved.
- A model must not be the sole oracle for whether its own generated artifact is correct.
- Comparison tolerances must be declared before execution.

## 9. Execution Procedure

1. Resolve exact source and test Skill versions.
2. Create isolated fixtures and record fingerprints.
3. Execute cases in severity order: Critical, High, Medium, Low.
4. Persist raw outputs before interpretation.
5. Re-run deterministic pass cases once to verify repeatability.
6. Evaluate the strictness profile and zero-tolerance conditions.
7. Publish a signed or content-addressed result bundle.

## 10. Failure Injection

Inject only controlled failures declared by each case. Preserve partial-write journals, correlation identifiers and raw dependency errors. Recovery testing must not grant extra permissions or mutate approved inputs.

## 11. Security and Tenant Isolation

All security and isolation findings are non-compensating. Cross-tenant leakage, privilege escalation, secret exposure, prompt-injection execution or user-owned overwrite fails the suite immediately.

## 12. Replay and Idempotency

Replay must preserve semantic outcomes. Duplicate requests, messages, generation units, migrations and resumed tasks must not duplicate protected side effects. A timeout with unknown completion status requires reconciliation rather than blind repetition.

## 13. Evidence Contract

Each result must include case identity, target versions, fixture fingerprints, raw tool/runner output, output fingerprints, policy decisions, trace links, approval records, start/end timestamps and the deterministic assertion result.

## 14. Anti-Fraud Rules

The suite must fail when a workflow attempts to pass by deleting or disabling tests, weakening assertions, changing approved requirements, suppressing security findings, fabricating evidence, converting a required real integration into a mock-only test, or hiding skips/quarantine.

## 15. Reporting

Publish JSON and human-readable summaries with counts by severity and category, failures, flaky cases, quarantines, waivers, uncovered targets, evidence completeness, runtime, resource consumption and release decision.

## 16. Acceptance Criteria

- All Critical cases pass.
- High-severity pass rate is at least 98%.
- Overall pass rate is at least 95%.
- Required evidence completeness is satisfied.
- No zero-tolerance condition occurs.
- Repeatability and coverage checks pass.
- Waivers are valid, owned, time-bounded and do not cover Critical or High failures.

## 17. Release Impact

A failed Critical case or anti-fraud signal blocks release. Other failures are evaluated by `references/STRICTNESS_PROFILE.json`; no aggregate score may compensate for a zero-tolerance defect.

## 18. Definition of Done

The test Skill is done only when every declared case has a terminal result, raw evidence is preserved, deterministic assertions are evaluated, direct coverage remains complete, the release decision is reproducible and the result bundle passes the result schema.
