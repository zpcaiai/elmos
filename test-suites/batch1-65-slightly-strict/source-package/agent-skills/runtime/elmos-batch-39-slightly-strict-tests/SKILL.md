---
name: elmos-batch-39-slightly-strict-tests
description: "Run the slightly strict Batch 39 test suite for Finance, billing, treasury and revenue operations."
version: 1.0.0
test_skill_id: T039
strictness_profile: elmos-slightly-strict-v1
case_count: 8
target_batches: [39]
source_package: elmos-skills-batch1-65-complete
---

# T039 — Finance, billing, treasury and revenue operations Slightly Strict Tests

## 1. Objective

Execute a deterministic, evidence-backed and moderately adversarial certification suite for **Finance, billing, treasury and revenue operations**. This suite is stricter than a smoke test but does not claim exhaustive formal verification.

## 2. Target Scope

- **Target Batch(es):** 39
- **Target product line(s):** legacy-modernization
- **Direct target Skill count:** 48

- `accounts-receivable-payment-allocation-refund-dispute-and-dunning`
- `bank-statement-iso20022-camt-bai2-ingestion-and-reconciliation`
- `beneficiary-bank-account-virtual-account-mandate-and-verification-of-payee`
- `billing-finance-reconciliation-period-close-audit-evidence-and-reporting`
- `budget-driver-based-planning-workforce-capex-opex-and-version-control`
- `cash-application-remittance-matching-allocation-and-unapplied-cash`
- `cash-forecast-scenario-variance-confidence-and-liquidity-planning`
- `cohort-retention-grr-nrr-survival-and-customer-lifecycle-analytics`
- `commercial-operations-renewal-expansion-churn-forecast-and-revenue-assurance`
- `contract-asset-liability-deferred-revenue-unbilled-ar-and-financial-subledger`
- `credit-policy-limit-risk-deposit-collection-writeoff-and-bad-debt`
- `customer-product-segment-profitability-ltv-cac-payback-and-cost-to-serve`
- `executive-finance-cockpit-ifrs18-mpm-board-pack-and-narrative`
- `finance-actual-plan-forecast-reconciliation-close-and-management-reporting`
- `finance-analytics-planning-unit-economics-orchestrator`
- `finance-analytics-quality-security-performance-and-release-gates`
- `finance-planning-workflow-owner-review-approval-lock-and-collaboration`
- `finance-semantic-layer-kpi-registry-definition-lineage-and-restatement`
- `financial-billing-commercial-operations-orchestrator`
- `financial-commercial-security-quality-chaos-and-release-gates`
- `focus-cost-ingestion-shared-cost-allocation-showback-chargeback-and-unit-cost`
- `fx-market-data-quote-trade-hedge-settlement-revaluation-and-exposure`
- `gross-margin-cogs-contribution-margin-and-cost-classification`
- `invoice-document-en16931-peppol-credit-note-delivery-and-acceptance`
- `meter-definition-dimension-aggregation-correction-and-data-quality`
- `mrr-arr-acv-tcv-bookings-billings-revenue-and-recurring-metric-engine`
- `multi-tenant-metering-event-contract-and-usage-ledger`
- `order-subscription-provisioning-entitlement-lifecycle-and-orchestration`
- `payment-fraud-risk-signal-rule-model-decision-case-and-step-up`
- `payment-routing-orchestration-fee-sla-retry-idempotency-and-failover`
- `payment-security-pci-tokenization-pan-vault-encryption-key-and-secret-boundary`
- `payment-treasury-conformance-security-chaos-performance-and-release-gates`
- `payment-treasury-financial-risk-operations-orchestrator`
- `payment-treasury-operations-cockpit-position-reconciliation-fraud-and-sla`
- `pricing-analytics-packaging-discount-waterfall-elasticity-and-experiment`
- `product-catalog-price-book-plan-rate-card-entitlement-discount-and-promotion`
- `psp-bank-payment-rail-connector-capability-authentication-and-lifecycle`
- `quote-cpq-contract-amendment-commitment-minimum-and-approval`
- `rating-charging-billing-period-invoice-line-and-adjustment-engine`
- `refund-reversal-return-chargeback-dispute-and-representment`
- `revenue-bridge-new-expansion-contraction-churn-reactivation-and-fx-waterfall`
- `revenue-recognition-ifrs15-asc606-performance-obligation-allocation-and-schedule`
- `rolling-forecast-scenario-assumption-sensitivity-confidence-and-stress-test`
- `tax-determination-registration-nexus-vat-gst-sales-tax-withholding-and-einvoicing`
- `treasury-bank-account-liquidity-pooling-sweep-limit-and-funding`
- `treasury-mandate-signer-approval-segregation-limit-and-payment-factory-control`
- `unified-payment-intent-instruction-attempt-settlement-and-cash-movement-domain`
- `variance-price-volume-mix-fx-timing-rate-and-driver-analysis`

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

### TC-T039-001 — Representative approved workflow completes end to end

- **Category:** `happy_path`
- **Severity:** `HIGH`
- **Setup:** Use a valid representative fixture covering the primary responsibilities of the target Batch. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Execute the Batch orchestrator or representative target Skills with approved inputs. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** All mandatory outputs validate, trace to inputs, and contain no hidden warnings or unsupported claims. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-002 — Boundary and moderate scale remain correct

- **Category:** `boundary`
- **Severity:** `MEDIUM`
- **Setup:** Use minimum/maximum supported sizes, empty optional collections, and a moderately large realistic fixture. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Execute the same workflow at declared boundaries and at 2x the normal reference volume. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Behavior remains bounded; limits are explicit; no silent truncation, quadratic blow-up, or inconsistent result occurs. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-003 — Malformed or contradictory input fails safely

- **Category:** `negative_input`
- **Severity:** `HIGH`
- **Setup:** Corrupt one required field, introduce one invalid reference, and add one contradictory constraint. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Submit the malformed fixture without granting an exception. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** The workflow rejects or blocks with a structured diagnostic and makes no authoritative partial success claim. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-004 — Dependency failure is contained and recoverable

- **Category:** `dependency_failure`
- **Severity:** `HIGH`
- **Setup:** Make one required provider, registry, model, runner, database, broker, or external dependency unavailable. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Execute until the failure is reached, then restore the dependency and resume where supported. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Failure classification is correct, partial writes are journaled, retry is bounded, and resume does not duplicate side effects. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-005 — Security, tenant and permission boundaries cannot be bypassed

- **Category:** `security_isolation`
- **Severity:** `CRITICAL`
- **Setup:** Create two tenants/projects and an actor lacking one required permission; include a malicious embedded instruction. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Attempt cross-boundary reads/writes, privilege escalation, and prompt-injection-driven tool use. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** All attempts are denied; no sensitive data leaks; the malicious instruction is treated as untrusted content and audited. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-006 — Replay and retry are idempotent

- **Category:** `replay_idempotency`
- **Severity:** `HIGH`
- **Setup:** Capture an accepted request, event, generation unit, migration step, or task with its idempotency identity. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Replay it twice, including once after an injected timeout where the original completion status is initially unknown. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** No duplicate semantic object or side effect is produced; the original result or safe reconciliation is returned. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-007 — Schema, runtime and dependency drift is detected

- **Category:** `version_drift`
- **Severity:** `HIGH`
- **Setup:** Change one upstream schema or tool version compatibly and one incompatibly. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Run compatibility resolution and the target workflow against both revisions. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Compatible evolution succeeds with evidence; incompatible evolution blocks with precise impact and migration guidance. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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

### TC-T039-008 — Tampered or incomplete evidence cannot produce a pass

- **Category:** `evidence_tamper`
- **Severity:** `CRITICAL`
- **Setup:** Remove one required evidence record and alter one stored output fingerprint. Batch theme: Finance, billing, treasury and revenue operations.
- **Stimulus:** Evaluate the run and attempt to publish a success or certification result. Exercise at least one orchestrating Skill and all directly affected target Skills.
- **Expected result:** Hash/signature or completeness checks fail and release remains blocked; no score averaging can hide the defect. Required Batch-specific contracts for Finance, billing, treasury and revenue operations remain satisfied.
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
