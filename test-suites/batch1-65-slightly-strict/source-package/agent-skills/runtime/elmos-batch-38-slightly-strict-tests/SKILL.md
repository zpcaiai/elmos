---
name: elmos-batch-38-slightly-strict-tests
description: "Run the slightly strict Batch 38 test suite for Governance, risk, compliance and policy automation."
version: 1.0.0
test_skill_id: T038
strictness_profile: elmos-slightly-strict-v1
case_count: 8
target_batches: [38]
source_package: elmos-skills-batch1-65-complete
---

# T038 — Governance, risk, compliance and policy automation Slightly Strict Tests

## 1. Objective

Execute a deterministic, evidence-backed and moderately adversarial certification suite for **Governance, risk, compliance and policy automation**. This suite is stricter than a smoke test but does not claim exhaustive formal verification.

## 2. Target Scope

- **Target Batch(es):** 38
- **Target product line(s):** legacy-modernization
- **Direct target Skill count:** 48

- `authoritative-policy-source-document-version-clause-and-citation-ingestion`
- `board-committee-agenda-pack-decision-minute-action-and-attestation`
- `compliance-calendar-deadline-recurrence-trigger-and-escalation`
- `continuous-authorization-pdp-pep-decision-api-obligations-and-cache`
- `control-as-code-oscal-objective-evidence-monitor-and-enforcement-binding`
- `control-automation-remediation-plan-approval-execution-compensation-and-verification`
- `cross-border-jurisdiction-entity-product-data-and-regulatory-matrix`
- `deontic-temporal-jurisdiction-exception-and-policy-intermediate-representation`
- `deployment-gate-artifact-provenance-sbom-test-risk-and-environment-admission`
- `exception-waiver-risk-acceptance-compensating-control-and-expiry`
- `governance-case-intake-triage-investigation-remediation-and-closure`
- `governance-operations-cockpit-sla-calendar-risk-board-and-regulator-reporting`
- `governance-records-retention-legal-hold-privilege-and-disposition`
- `governance-regulatory-operations-orchestrator`
- `kubernetes-cel-gatekeeper-kyverno-image-and-workload-admission-policy`
- `natural-language-policy-clause-definition-entity-and-scope-extraction`
- `obligation-workplan-evidence-certification-attestation-and-closure`
- `policy-as-code-repository-bundle-signing-distribution-and-offline-cache`
- `policy-change-impact-shadow-canary-rollout-kill-switch-and-rollback`
- `policy-conflict-redundancy-gap-shadowing-and-satisfiability-analysis`
- `policy-conformance-fuzz-property-security-chaos-performance-and-release-gates`
- `policy-control-continuous-authorization-orchestrator`
- `policy-copilot-grounded-rag-drafting-formalization-and-review-assistant`
- `policy-decision-log-explanation-trace-replay-attestation-and-evidence`
- `policy-explainability-source-trace-counterfactual-and-audience-views`
- `policy-governance-operations-inventory-ownership-debt-sla-and-cockpit`
- `policy-information-point-context-fact-resolver-trust-freshness-and-external-data`
- `policy-intelligence-conformance-security-quality-chaos-and-release-gates`
- `policy-intelligence-evaluation-gold-corpus-benchmark-red-team-and-model-governance`
- `policy-intelligence-governance-engineering-orchestrator`
- `policy-ir-to-rego-cedar-cel-legalruleml-and-control-code-compiler`
- `policy-knowledge-search-question-answering-and-cross-framework-traceability`
- `policy-mining-decision-log-code-config-grant-and-exception-discovery`
- `policy-ontology-knowledge-graph-rdf-owl-shacl-and-projection`
- `policy-review-comment-approval-segregation-of-duties-and-publication`
- `policy-training-targeting-acknowledgement-competency-and-campaign`
- `rego-cedar-cel-policy-authoring-lint-test-simulation-and-partial-evaluation`
- `regulator-portal-correspondence-submission-provider-and-delivery-adapters`
- `regulatory-change-source-monitoring-semantic-diff-and-impact-analysis`
- `regulatory-examination-inquiry-evidence-room-response-and-remediation`
- `regulatory-notification-incident-disclosure-materiality-and-deadline-workflow`
- `regulatory-obligation-register-source-applicability-and-lifecycle`
- `regulatory-operations-conformance-security-chaos-and-release-gates`
- `regulatory-reporting-taxonomy-xbrl-filing-validation-and-acknowledgement`
- `responsibility-raci-accountability-delegation-and-capacity-governance`
- `runtime-gate-api-service-mesh-database-tool-sandbox-runner-and-artifact-enforcement`
- `shared-signals-caep-risc-session-token-device-workload-and-risk-reevaluation`
- `unified-policy-domain-language-engine-contract-and-lifecycle`

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

### TC-T038-001 — Representative approved workflow completes end to end

- **Category:** `happy_path`
- **Severity:** `HIGH`
- **Setup:** Use a valid representative fixture covering the primary responsibilities of the target Batch. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Execute the Batch orchestrator or representative target Skills with approved inputs. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** All mandatory outputs validate, trace to inputs, and contain no hidden warnings or unsupported claims. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-002 — Boundary and moderate scale remain correct

- **Category:** `boundary`
- **Severity:** `MEDIUM`
- **Setup:** Use minimum/maximum supported sizes, empty optional collections, and a moderately large realistic fixture. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Execute the same workflow at declared boundaries and at 2x the normal reference volume. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Behavior remains bounded; limits are explicit; no silent truncation, quadratic blow-up, or inconsistent result occurs. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-003 — Malformed or contradictory input fails safely

- **Category:** `negative_input`
- **Severity:** `HIGH`
- **Setup:** Corrupt one required field, introduce one invalid reference, and add one contradictory constraint. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Submit the malformed fixture without granting an exception. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** The workflow rejects or blocks with a structured diagnostic and makes no authoritative partial success claim. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-004 — Dependency failure is contained and recoverable

- **Category:** `dependency_failure`
- **Severity:** `HIGH`
- **Setup:** Make one required provider, registry, model, runner, database, broker, or external dependency unavailable. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Execute until the failure is reached, then restore the dependency and resume where supported. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Failure classification is correct, partial writes are journaled, retry is bounded, and resume does not duplicate side effects. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-005 — Security, tenant and permission boundaries cannot be bypassed

- **Category:** `security_isolation`
- **Severity:** `CRITICAL`
- **Setup:** Create two tenants/projects and an actor lacking one required permission; include a malicious embedded instruction. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Attempt cross-boundary reads/writes, privilege escalation, and prompt-injection-driven tool use. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** All attempts are denied; no sensitive data leaks; the malicious instruction is treated as untrusted content and audited. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-006 — Replay and retry are idempotent

- **Category:** `replay_idempotency`
- **Severity:** `HIGH`
- **Setup:** Capture an accepted request, event, generation unit, migration step, or task with its idempotency identity. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Replay it twice, including once after an injected timeout where the original completion status is initially unknown. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** No duplicate semantic object or side effect is produced; the original result or safe reconciliation is returned. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-007 — Schema, runtime and dependency drift is detected

- **Category:** `version_drift`
- **Severity:** `HIGH`
- **Setup:** Change one upstream schema or tool version compatibly and one incompatibly. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Run compatibility resolution and the target workflow against both revisions. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Compatible evolution succeeds with evidence; incompatible evolution blocks with precise impact and migration guidance. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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

### TC-T038-008 — Tampered or incomplete evidence cannot produce a pass

- **Category:** `evidence_tamper`
- **Severity:** `CRITICAL`
- **Setup:** Remove one required evidence record and alter one stored output fingerprint. Batch theme: Governance, risk, compliance and policy automation.
- **Stimulus:** Evaluate the run and attempt to publish a success or certification result. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Hash/signature or completeness checks fail and release remains blocked; no score averaging can hide the defect. Required Batch-specific contracts for Governance, risk, compliance and policy automation remain satisfied.
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
