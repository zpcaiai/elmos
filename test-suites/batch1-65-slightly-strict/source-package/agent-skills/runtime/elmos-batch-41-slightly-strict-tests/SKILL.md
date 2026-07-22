---
name: elmos-batch-41-slightly-strict-tests
description: "Run the slightly strict Batch 41 test suite for Product discovery and product-management operations."
version: 1.0.0
test_skill_id: T041
strictness_profile: elmos-slightly-strict-v1
case_count: 8
target_batches: [41]
source_package: elmos-skills-batch1-65-complete
---

# T041 — Product discovery and product-management operations Slightly Strict Tests

## 1. Objective

Execute a deterministic, evidence-backed and moderately adversarial certification suite for **Product discovery and product-management operations**. This suite is stricter than a smoke test but does not claim exhaustive formal verification.

## 2. Target Scope

- **Target Batch(es):** 41
- **Target product line(s):** legacy-modernization
- **Direct target Skill count:** 48

- `product-discovery-analytics-kpi-scoring-forecast-and-diagnostics`
- `product-discovery-audit-evidence-records-retention-and-legal-hold`
- `product-discovery-automation-copilot-recommendation-and-human-review`
- `product-discovery-backfill-replay-resilience-disaster-recovery-and-continuity`
- `product-discovery-case-investigation-remediation-and-closure`
- `product-discovery-data-quality-dedup-reconciliation-and-certification`
- `product-discovery-domain-model-lifecycle-and-state-machine`
- `product-discovery-intake-ingestion-connector-sync-and-idempotency`
- `product-discovery-master-data-identity-hierarchy-and-effective-dating`
- `product-discovery-observability-sla-cockpit-alerting-and-operations`
- `product-discovery-orchestrator`
- `product-discovery-planning-capacity-scenario-optimization-and-allocation`
- `product-discovery-policy-authorization-approval-segregation-and-exception`
- `product-discovery-provider-adapters-versioning-compatibility-and-migration`
- `product-discovery-security-privacy-quality-performance-chaos-and-release-gates`
- `product-discovery-workflow-orchestration-assignment-escalation-and-recovery`
- `product-launch-analytics-kpi-scoring-forecast-and-diagnostics`
- `product-launch-audit-evidence-records-retention-and-legal-hold`
- `product-launch-automation-copilot-recommendation-and-human-review`
- `product-launch-backfill-replay-resilience-disaster-recovery-and-continuity`
- `product-launch-case-investigation-remediation-and-closure`
- `product-launch-data-quality-dedup-reconciliation-and-certification`
- `product-launch-domain-model-lifecycle-and-state-machine`
- `product-launch-intake-ingestion-connector-sync-and-idempotency`
- `product-launch-master-data-identity-hierarchy-and-effective-dating`
- `product-launch-observability-sla-cockpit-alerting-and-operations`
- `product-launch-orchestrator`
- `product-launch-planning-capacity-scenario-optimization-and-allocation`
- `product-launch-policy-authorization-approval-segregation-and-exception`
- `product-launch-provider-adapters-versioning-compatibility-and-migration`
- `product-launch-security-privacy-quality-performance-chaos-and-release-gates`
- `product-launch-workflow-orchestration-assignment-escalation-and-recovery`
- `product-portfolio-analytics-kpi-scoring-forecast-and-diagnostics`
- `product-portfolio-audit-evidence-records-retention-and-legal-hold`
- `product-portfolio-automation-copilot-recommendation-and-human-review`
- `product-portfolio-backfill-replay-resilience-disaster-recovery-and-continuity`
- `product-portfolio-case-investigation-remediation-and-closure`
- `product-portfolio-data-quality-dedup-reconciliation-and-certification`
- `product-portfolio-domain-model-lifecycle-and-state-machine`
- `product-portfolio-intake-ingestion-connector-sync-and-idempotency`
- `product-portfolio-master-data-identity-hierarchy-and-effective-dating`
- `product-portfolio-observability-sla-cockpit-alerting-and-operations`
- `product-portfolio-orchestrator`
- `product-portfolio-planning-capacity-scenario-optimization-and-allocation`
- `product-portfolio-policy-authorization-approval-segregation-and-exception`
- `product-portfolio-provider-adapters-versioning-compatibility-and-migration`
- `product-portfolio-security-privacy-quality-performance-chaos-and-release-gates`
- `product-portfolio-workflow-orchestration-assignment-escalation-and-recovery`

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

### TC-T041-001 — Representative approved workflow completes end to end

- **Category:** `happy_path`
- **Severity:** `HIGH`
- **Setup:** Use a valid representative fixture covering the primary responsibilities of the target Batch. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Execute the Batch orchestrator or representative target Skills with approved inputs. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** All mandatory outputs validate, trace to inputs, and contain no hidden warnings or unsupported claims. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-002 — Boundary and moderate scale remain correct

- **Category:** `boundary`
- **Severity:** `MEDIUM`
- **Setup:** Use minimum/maximum supported sizes, empty optional collections, and a moderately large realistic fixture. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Execute the same workflow at declared boundaries and at 2x the normal reference volume. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Behavior remains bounded; limits are explicit; no silent truncation, quadratic blow-up, or inconsistent result occurs. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-003 — Malformed or contradictory input fails safely

- **Category:** `negative_input`
- **Severity:** `HIGH`
- **Setup:** Corrupt one required field, introduce one invalid reference, and add one contradictory constraint. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Submit the malformed fixture without granting an exception. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** The workflow rejects or blocks with a structured diagnostic and makes no authoritative partial success claim. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-004 — Dependency failure is contained and recoverable

- **Category:** `dependency_failure`
- **Severity:** `HIGH`
- **Setup:** Make one required provider, registry, model, runner, database, broker, or external dependency unavailable. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Execute until the failure is reached, then restore the dependency and resume where supported. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Failure classification is correct, partial writes are journaled, retry is bounded, and resume does not duplicate side effects. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-005 — Security, tenant and permission boundaries cannot be bypassed

- **Category:** `security_isolation`
- **Severity:** `CRITICAL`
- **Setup:** Create two tenants/projects and an actor lacking one required permission; include a malicious embedded instruction. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Attempt cross-boundary reads/writes, privilege escalation, and prompt-injection-driven tool use. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** All attempts are denied; no sensitive data leaks; the malicious instruction is treated as untrusted content and audited. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-006 — Replay and retry are idempotent

- **Category:** `replay_idempotency`
- **Severity:** `HIGH`
- **Setup:** Capture an accepted request, event, generation unit, migration step, or task with its idempotency identity. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Replay it twice, including once after an injected timeout where the original completion status is initially unknown. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** No duplicate semantic object or side effect is produced; the original result or safe reconciliation is returned. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-007 — Schema, runtime and dependency drift is detected

- **Category:** `version_drift`
- **Severity:** `HIGH`
- **Setup:** Change one upstream schema or tool version compatibly and one incompatibly. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Run compatibility resolution and the target workflow against both revisions. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Compatible evolution succeeds with evidence; incompatible evolution blocks with precise impact and migration guidance. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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

### TC-T041-008 — Tampered or incomplete evidence cannot produce a pass

- **Category:** `evidence_tamper`
- **Severity:** `CRITICAL`
- **Setup:** Remove one required evidence record and alter one stored output fingerprint. Batch theme: Product discovery and product-management operations.
- **Stimulus:** Evaluate the run and attempt to publish a success or certification result. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Hash/signature or completeness checks fail and release remains blocked; no score averaging can hide the defect. Required Batch-specific contracts for Product discovery and product-management operations remain satisfied.
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
